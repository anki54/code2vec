import tensorflow as tf
from tensorflow.python import keras
from tensorflow.python.keras.metrics import Metric
import tensorflow.python.keras.backend as K
from tensorflow.python.keras.backend import init_ops, math_ops, control_flow_ops, state_ops
from tensorflow.python.ops import string_ops
import abc
from typing import Optional, Callable, List
from functools import reduce
from common import common
from vocabularies import SpecialVocabWords


class WordsSubtokenMetricBase(Metric):
    FilterType = Callable[[tf.Tensor, tf.Tensor], tf.Tensor]

    def __init__(self,
                 index_to_word_table: Optional[tf.contrib.lookup.HashTable] = None,
                 topk_predicted_words=None,
                 predicted_words_filters: Optional[List[FilterType]] = None,
                 subtokens_delimiter: str = '|', name=None, dtype=None):
        super(WordsSubtokenMetricBase, self).__init__(name=name, dtype=dtype)
        self.tp = self.add_weight('true_positives', shape=(), initializer=init_ops.zeros_initializer)
        self.fp = self.add_weight('false_positives', shape=(), initializer=init_ops.zeros_initializer)
        self.fn = self.add_weight('false_negatives', shape=(), initializer=init_ops.zeros_initializer)
        self.index_to_word_table = index_to_word_table
        self.topk_predicted_words = topk_predicted_words
        self.predicted_words_filters = predicted_words_filters
        self.subtokens_delimiter = subtokens_delimiter

    def _get_true_target_word_string(self, true_target_word):
        if self.index_to_word_table is None:
            return true_target_word
        true_target_word_index = tf.cast(true_target_word, dtype=self.index_to_word_table.key_dtype)
        return self.index_to_word_table.lookup(true_target_word_index)

    def update_state(self, true_target_word, predictions, sample_weight=None):
        """Accumulates true positive, false positive and false negative statistics."""
        if sample_weight is not None:
            raise NotImplemented("WordsSubtokenMetricBase with non-None `sample_weight` is not implemented.")

        # For each example in the batch we have:
        #     (i)  one ground true target word;
        #     (ii) one predicted word (argmax y_hat)

        topk_predicted_words = predictions if self.topk_predicted_words is None else self.topk_predicted_words
        assert topk_predicted_words is not None
        predicted_word = self._get_prediction_from_topk(topk_predicted_words)

        true_target_word_string = self._get_true_target_word_string(true_target_word)
        true_target_word_string = tf.reshape(true_target_word_string, [-1])

        # We split each word into subtokens
        true_target_subwords = string_ops.string_split(true_target_word_string, delimiter=self.subtokens_delimiter)
        prediction_subwords = string_ops.string_split(predicted_word, delimiter=self.subtokens_delimiter)
        true_target_subwords = tf.sparse.to_dense(true_target_subwords, default_value=SpecialVocabWords.PAD)
        prediction_subwords = tf.sparse.to_dense(prediction_subwords, default_value=SpecialVocabWords.PAD)
        true_target_subwords_mask = tf.not_equal(true_target_subwords, SpecialVocabWords.PAD)
        prediction_subwords_mask = tf.not_equal(prediction_subwords, SpecialVocabWords.PAD)
        # Now shapes of true_target_subwords & true_target_subwords are (batch, subtokens)

        # We use broadcast to calculate 2 lists difference with duplicates preserving.
        true_target_subwords = tf.expand_dims(true_target_subwords, -1)
        prediction_subwords = tf.expand_dims(prediction_subwords, -1)
        # Now shapes of true_target_subwords & true_target_subwords are (batch, subtokens, 1)
        true_target_subwords__in__prediction_subwords = \
            tf.reduce_any(tf.equal(true_target_subwords, tf.transpose(prediction_subwords, perm=[0, 2, 1])), axis=2)
        prediction_subwords__in__true_target_subwords = \
            tf.reduce_any(tf.equal(prediction_subwords, tf.transpose(true_target_subwords, perm=[0, 2, 1])), axis=2)

        # Count ground true label subwords that exist in the predicted word.
        batch_true_positive = tf.reduce_sum(tf.cast(
            tf.logical_and(prediction_subwords__in__true_target_subwords, prediction_subwords_mask), tf.float32))
        # Count ground true label subwords that don't exist in the predicted word.
        batch_false_positive = tf.reduce_sum(tf.cast(
            tf.logical_and(~prediction_subwords__in__true_target_subwords, prediction_subwords_mask), tf.float32))
        # Count predicted word subwords that don't exist in the ground true label.
        batch_false_negative = tf.reduce_sum(tf.cast(
            tf.logical_and(~true_target_subwords__in__prediction_subwords, true_target_subwords_mask), tf.float32))

        update_ops = [
            state_ops.assign_add(self.tp, batch_true_positive),
            state_ops.assign_add(self.fp, batch_false_positive),
            state_ops.assign_add(self.fn, batch_false_negative)
        ]
        return control_flow_ops.group(update_ops)

    def _get_prediction_from_topk(self, topk_predicted_words):
        # apply given filter
        masks = []
        if self.predicted_words_filters is not None:
            masks = [fltr(topk_predicted_words) for fltr in self.predicted_words_filters]
        if masks:
            # assert all(mask.shape.assert_is_compatible_with(top_k_pred_indices) for mask in masks)
            legal_predicted_target_words_mask = reduce(tf.logical_and, masks)
        else:
            legal_predicted_target_words_mask = tf.cast(tf.ones_like(topk_predicted_words), dtype=tf.bool)

        # the first legal predicted word is our prediction
        first_legal_predicted_target_word_mask = common.tf_get_first_true(legal_predicted_target_words_mask)
        first_legal_predicted_target_word_idx = tf.where(first_legal_predicted_target_word_mask)
        first_legal_predicted_word_string = tf.gather_nd(topk_predicted_words,
                                                         first_legal_predicted_target_word_idx)

        prediction = tf.reshape(first_legal_predicted_word_string, [-1])
        return prediction

    @abc.abstractmethod
    def result(self):
        ...

    def reset_states(self):
        for v in self.variables:
            K.set_value(v, 0)


class WordsSubtokenPrecisionMetric(WordsSubtokenMetricBase):
    def result(self):
        precision = math_ops.div_no_nan(self.tp, self.tp + self.fp)
        return precision


class WordsSubtokenRecallMetric(WordsSubtokenMetricBase):
    def result(self):
        recall = math_ops.div_no_nan(self.tp, self.tp + self.fn)
        return recall


class WordsSubtokenF1Metric(WordsSubtokenMetricBase):
    def result(self):
        recall = math_ops.div_no_nan(self.tp, self.tp + self.fn)
        precision = math_ops.div_no_nan(self.tp, self.tp + self.fp)
        f1 = math_ops.div_no_nan(2 * precision * recall, precision + recall + K.epsilon())
        return f1
