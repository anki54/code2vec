import os
import subprocess
import csv
import xml.etree.ElementTree as ET

file_path='dataset/data/csharp/000'
vul=[]

def csharp_lable_vul():
    xml_file='manifest-105-IEIiZm.xml'
    tree = ET.parse(xml_file)
    root = tree.getroot()
    for child in root.iter('file'):
        for flaw in child.findall('flaw'):
            file_path= child.attrib['path'].split('/')[3]
            print(file_path)
            vul.append(file_path)

def process_dir(sard_file_path):
    for input_filename in os.listdir(sard_file_path):
        if os.path.isdir(sard_file_path+'/'+input_filename):
            process_dir(sard_file_path+'/'+input_filename)
        elif '.vector' in input_filename:
            process_vector(sard_file_path)
            #process_c2v(sard_file_path,input_filename)

def process_vector(sard_file_path):
    count=0
    cs_file=''
    files = os.listdir(sard_file_path)
    for file_p in files:
        if '.cs' in file_p:
            count+=1
            cs_file=file_p
    if count>1:
        print('Too many cs files: ')
        f = open('extra.txt','a')
        f.write(sard_file_path+'\n')
        f.close()
    elif count==1:
        # process vector file
        print('Writing vector file ' + str(cs_file))
        vector_data_op = csv.writer(open(vector_data,'a',newline=''),delimiter=',')
        vector = open(sard_file_path+'/csharp.data.c2v.vectors','r').readlines()
        len_file = len(vector)
        if len_file<=0:
            print('skipping empty file')            
            f = open('empty.txt','a')
            f.write(sard_file_path+'\n')
            f.close()
        else:
            label = 0
            if cs_file in vul:
                label=1 
            vector_data_op.writerow([cs_file,vector[0].rstrip(),label])
                

def process_file(code_file):
    print(code_file)
    #subprocess.call(['./csharp_interactive.sh',str(code_file)])
    os.system('python code2vec.py --load models/sharp/saved_model_iter33 --test ' + code_file+ '/csharp.data.c2v --export_code_vectors')

def process_c2v(dir_name, c2v_file):
    meta_data = csv.writer(open(meta_data_file,'a',newline=''),delimiter=',') 
    vetcor_data = open(c2v_data,'a') 
    lines=open(dir_name + '/' + c2v_file,'r').readlines()    
    current_vector = lines[0]
    vetcor_data.write(current_vector+'\n')
    vul=0
    for dir_file in os.listdir(dir_name):
        if '.cs' in dir_file:
            meta_data.writerow([dir_file,current_vector,vul])            
    #vector_data.close()

c2v_data='csharp.data.c2v'
meta_data_file='csharp_meta_data.csv'
vector_data = 'csharp_data.csv'
csharp_lable_vul()
process_dir(file_path)

