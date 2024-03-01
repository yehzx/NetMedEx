import re
import sys
import getopt

#Get dictionary key
def get_key (dict, value):
    for k, v in dict.items():
        if v == value:
            return k

#Get dictionary multiple key
def get_key_list (dict, value):
    k_list = []
    for k, v in dict.items():
        if v == value:
            k_list.append(k)
    return k_list 

#Get command line argument
try:
    opts, args = getopt.getopt(sys.argv[1:], "-i:-w:-c:",  ["inputfile=", "cutweihgt=", "custom="])
    for name, value in opts:
        if name in ('-i', '--inputfile'):
            file_name = value
        elif name in ('-w', '--cutweihgt'):
            cut_weight = value
        elif name in ('-c', '--custom'):
            custom_file = value
except getopt.GetoptError:
    print(f'''Usage:{sys.argv[0]}
      -i Input file path
      -w Edge weight value
      -c Custom file path
      ''')
    sys.exit()

#Passer custom file
if len(opts) > 2:
    custom_set = set()
    custom_dict = {}
    cus_count = 0
    syn_dict = {}
    with open(custom_file,'r') as custom_line:
        for line in custom_line:
            line = line.strip()
            if re.search('\=', line):
                syn_1, syn_2 = line.split('=')
                custom_set.add(syn_1)
                custom_set.add(syn_2)
                syn_dict[syn_2.lower()] = syn_1.lower()
                custom_dict[syn_1.lower()] = 'custom_' + str(cus_count)
            else:
                custom_set.add(line)
                custom_set.add(line.lower())
                cus_count += 1
                custom_dict[line.lower()] = 'custom_' + str(cus_count)

#Passer pubtator file
id_dict = {}
count_id = {}

with open(file_name,'r') as pubtator_pre:
    for line in pubtator_pre:
        if line == '\n':
            next
        else:
            line = line.strip('\n')
            if re.search('\|t\|', line):
                next
            elif re.search('\|a\|', line):
                next
            else:
                #####################
                # 2024/02/27 PubTator3 compatible
                if len(line.split('\t')) == 4:
                    continue
                #####################
                if(line.split('\t')[5] == ''):
                    #print(line)
                    line = line + '-'
                if line.split('\t')[5] != '-':
                    if line.split('\t')[5] in id_dict:
                        count_id[line.split('\t')[5]] = count_id[line.split('\t')[5]] + 1
                        if(id_dict[line.split('\t')[5]] != line.split('\t')[4] + '$' + line.split('\t')[3].lower()):
                            cla, name = id_dict[line.split('\t')[5]].split('$')
                            if(cla != line.split('\t')[4]):
                                print('Exist the same id name in different class.')
                                print(id_dict[line.split('\t')[5]])
                                print(line.split('\t')[4] + '$' + line.split('\t')[3].lower())
                        if(len(id_dict[line.split('\t')[5]]) < len(line.split('\t')[4] + '$' + line.split('\t')[3].lower())):
                            id_dict[line.split('\t')[5]] = line.split('\t')[4] + '$' + line.split('\t')[3].lower()
                    else:
                        id_dict[line.split('\t')[5]] = line.split('\t')[4] + '$' + line.split('\t')[3].lower()
                        count_id[line.split('\t')[5]] = 1
                
                if line.split('\t')[5] == '9606' and line.split('\t')[4] == 'Species':
                    id_dict[line.split('\t')[5]] = line.split('\t')[4] + '$' + 'human'

new_id_dict = {}
for id_name in id_dict.values():
    key_list = get_key_list(id_dict, id_name)
    if(len(key_list) > 1):
        max_count = 0
        for k in key_list:
            if count_id[k] > max_count:
                max_k = k
        new_id_dict[max_k] = id_name
    else:
        new_id_dict[key_list[0]] = id_name

pubmed_id_set = set()
class_dict = {}
temp_class_dict = {}
class_pubmed_dict = {}
pubmed_id_set = set()
pubtator_set = set()
node_set = set()
n_word = ''
with open(file_name,'r') as pubtator:
    for line in pubtator:
        if line == '\n':
            uni_list = list(pubtator_set)
            for i in range(0, len(uni_list), 1):
                pubmed_id_1 = uni_list[i].split('#')[0]
                node_1 = uni_list[i].split('#')[1]
                name_id_1 = uni_list[i].split('#')[2]
                for j in range(i+1, len(uni_list), 1):
                    pubmed_id_2 = uni_list[j].split('#')[0]
                    node_2 = uni_list[j].split('#')[1]
                    name_id_2 = uni_list[j].split('#')[2]
                    if(uni_list[i] == uni_list[j]):
                        next
                    else:
                        pair_key = str(node_1)+'\t'+str(name_id_1)+'%'+str(node_2)+'\t'+str(name_id_2)+'%'+str(pubmed_id_1)
                        temp_class_dict[pair_key] = 1
            for key in temp_class_dict.keys():
                n_1 = key.split('%')[0]
                n_2 = key.split('%')[1]
                pub_id = key.split('%')[2]
                cla_name_1, id_num_1 = n_1.split('\t')
                cla_name_2, id_num_2 = n_2.split('\t')
                if(cla_name_1 in new_id_dict.values()):
                    n_1 = str(cla_name_1) + '\t' + str(get_key(new_id_dict, cla_name_1))
                if(cla_name_2 in new_id_dict.values()):
                    n_2 = str(cla_name_2) + '\t' + str(get_key(new_id_dict, cla_name_2))
                node_set.add(n_1)
                node_set.add(n_2)
                pair_1 = n_1+'\t'+n_2
                pair_2 = n_2+'\t'+n_1
                if pair_1 in class_dict.keys():
                    class_dict[pair_1] += 1
                    class_pubmed_dict[pair_1] = str(class_pubmed_dict[pair_1])+', '+str(pub_id)
                    next
                elif pair_2 in class_dict.keys():
                    class_dict[pair_2] += 1
                    class_pubmed_dict[pair_2] = str(class_pubmed_dict[pair_2])+', '+str(pub_id)
                    next
                else:
                    class_dict[pair_1] = 1
                    class_pubmed_dict[pair_1] = str(pub_id)
            temp_class_dict = {}
            pubtator_set = set()            
        else:
            line = line.strip('\n')
            if re.search('\|t\|', line):
                pubmed_id_set.add(line.split('|t|')[0])
                if len(opts) > 2:
                    for word in custom_set:
                        if re.search(word, line.split('|t|')[1]):
                            if(word.lower() in syn_dict.keys()):
                                n_word = syn_dict[word.lower()]
                                pubtator_set.add(line.split('|t|')[0]+'#'+custom_dict[n_word.lower()]+'$' + n_word.lower()+'#'+'-')
                            else:
                                pubtator_set.add(line.split('|t|')[0]+'#'+custom_dict[word.lower()]+'$' + word.lower()+'#'+'-')
            elif re.search('\|a\|', line):
                if len(opts) > 2:
                    for word in custom_set:
                        if re.search(word, line.split('|a|')[1]):
                            if(word.lower() in syn_dict.keys()):
                                n_word = syn_dict[word.lower()]
                                pubtator_set.add(line.split('|a|')[0]+'#'+custom_dict[n_word.lower()]+'$' + n_word.lower()+'#'+'-')
                            else:
                                pubtator_set.add(line.split('|a|')[0]+'#'+custom_dict[word.lower()]+'$' + word.lower()+'#'+'-')
            else:
                #####################
                # 2024/02/27 PubTator3 compatible
                if len(line.split('\t')) == 4:
                    continue
                #####################
                if(line.split('\t')[5] == ''):
                    line = line + '-'
                if line.split('\t')[5] in id_dict.keys():
                    node_name = id_dict[line.split('\t')[5]]
                    pubtator_set.add(line.split('\t')[0]+'#'+node_name+'#'+line.split('\t')[5])
                elif line.split('\t')[4] + '$' + line.split('\t')[3].lower() in id_dict.values():
                    pubtator_set.add(line.split('\t')[0]+'#'+line.split('\t')[4] + '$' + line.split('\t')[3].lower()+'#'+str(get_key(new_id_dict, line.split('\t')[4] + '$' + line.split('\t')[3].lower())))
                else:
                    pubtator_set.add(line.split('\t')[0]+'#'+line.split('\t')[4] + '$' + line.split('\t')[3].lower()+'#'+line.split('\t')[5])

weight_list = class_dict.values()

#Write edge file
with open(str(file_name) + '_edge.txt', 'w') as pubtator_e:
    for name in class_dict.keys():
        start = 1
        end = 20
        width = end - start
        scale_weight = int((class_dict[name]-min(weight_list))/(max(weight_list)-min(weight_list)) * width + start)
        pubtator_e.write(str(name)+'\t'+str(class_dict[name])+'\t'+str(scale_weight)+'\t'+str(class_pubmed_dict[name])+'\n')

#Write node file
with open(str(file_name) + '_node.txt', 'w') as pubtator_n:
    for name in node_set:
        pubtator_n.write(str(name)+'\n')

#Initial xgmml title
title = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
in_graphics = '<graphics><att name="NETWORK_WIDTH" value="795.0" type="string" cy:type="String"/><att name="NETWORK_DEPTH" value="0.0" type="string" cy:type="String"/><att name="NETWORK_HEIGHT" value="500.0" type="string" cy:type="String"/><att name="NETWORK_NODE_SELECTION" value="true" type="string" cy:type="String"/><att name="NETWORK_EDGE_SELECTION" value="true" type="string" cy:type="String"/><att name="NETWORK_BACKGROUND_PAINT" value="#FFFFFF" type="string" cy:type="String"/><att name="NETWORK_CENTER_Z_LOCATION" value="0.0" type="string" cy:type="String"/><att name="NETWORK_NODE_LABEL_SELECTION" value="false" type="string" cy:type="String"/><att name="NETWORK_TITLE" value="" type="string" cy:type="String"/></graphics>'

node_list = set()
node_dict = {}
with open(str(file_name) + '_node.txt','r') as node_file:
    for line in node_file:
        node_list.add(str.strip(line))
element_id = 1
for node_str in node_list:
    element_id += 1
    if(len(node_str.split('\t')) < 2):
        print(node_str)
    cla_name, name_id = node_str.split('\t')
    if(cla_name in node_dict.keys()):
        print(cla_name)
    if('&' in cla_name):
        cla_name = cla_name.replace('&', ' and ')
    if('"' in cla_name):
        cla_name = cla_name.replace('"', '')
    node_dict[cla_name] = str(element_id)

#xgmml edge format
in_edge = ''
edge_count = 0
edge_list = set()
show_node = set()
with open(str(file_name) + '_edge.txt','r') as edge_file:
    for line in edge_file:
        edge_list.add(str.strip(line))
for edge_str in edge_list:
    temp_edge = ''
    element_id += 1
    cla_1_edge_1, edge_1_id, cla_2_edge_2, edge_2_id, weight, scale_weight, pubmed_list = edge_str.split('\t')
    if(int(weight) >= int(cut_weight)):
        edge_count += 1
        if('&' in cla_1_edge_1):
            cla_1_edge_1 = cla_1_edge_1.replace('&', ' and ')
        if('&' in cla_2_edge_2):
            cla_2_edge_2 = cla_2_edge_2.replace('&', ' and ')
        if('"' in cla_1_edge_1):
            cla_1_edge_1 = cla_1_edge_1.replace('"', '')
        if('"' in cla_2_edge_2):
            cla_2_edge_2 = cla_2_edge_2.replace('"', '')
        cal_1, edge_1 = cla_1_edge_1.split('$')
        cal_2, edge_2 = cla_2_edge_2.split('$')
        show_node.add(cal_1 + '$' + edge_1 + '\t' + edge_1_id)
        show_node.add(cal_2 + '$' + edge_2 + '\t' + edge_2_id)
        temp_edge = '<edge id="'+ str(element_id) +'" label="'+ edge_1 +' (interacts with) '+ edge_2 +'" source="'+ node_dict[cla_1_edge_1] +'" target="'+ node_dict[cla_2_edge_2] +'" cy:directed="1"><att name="shared name" value="'+ edge_1 +' (interacts with) '+ edge_2 +'" type="string" cy:type="String"/><att name="shared interaction" value="interacts with" type="string" cy:type="String"/><att name="name" value="'+ edge_1 +' (interacts with) '+ edge_2 +'" type="string" cy:type="String"/><att name="selected" value="0" type="boolean" cy:type="Boolean"/><att name="interaction" value="interacts with" type="string" cy:type="String"/><att name="weight" value="'+ weight +'" type="integer" cy:type="Integer"/><att name="scale weight" value="'+ scale_weight +'" type="integer" cy:type="Integer"/><att name="pubmed id" value="'+ pubmed_list +'" type="string" cy:type="String"/><graphics width="'+ scale_weight +'" fill="#848484"><att name="EDGE_TOOLTIP" value="" type="string" cy:type="String"/><att name="EDGE_SELECTED" value="false" type="string" cy:type="String"/><att name="EDGE_TARGET_ARROW_SIZE" value="6.0" type="string" cy:type="String"/><att name="EDGE_LABEL" value="" type="string" cy:type="String"/><att name="EDGE_LABEL_TRANSPARENCY" value="255" type="string" cy:type="String"/><att name="EDGE_STACKING_DENSITY" value="0.5" type="string" cy:type="String"/><att name="EDGE_TARGET_ARROW_SHAPE" value="NONE" type="string" cy:type="String"/><att name="EDGE_SOURCE_ARROW_UNSELECTED_PAINT" value="#000000" type="string" cy:type="String"/><att name="EDGE_TARGET_ARROW_SELECTED_PAINT" value="#FFFF00" type="string" cy:type="String"/><att name="EDGE_TARGET_ARROW_UNSELECTED_PAINT" value="#000000" type="string" cy:type="String"/><att name="EDGE_SOURCE_ARROW_SHAPE" value="NONE" type="string" cy:type="String"/><att name="EDGE_BEND" value="" type="string" cy:type="String"/><att name="EDGE_STACKING" value="AUTO_BEND" type="string" cy:type="String"/><att name="EDGE_LABEL_COLOR" value="#000000" type="string" cy:type="String"/><att name="EDGE_TRANSPARENCY" value="255" type="string" cy:type="String"/><att name="EDGE_LABEL_ROTATION" value="0.0" type="string" cy:type="String"/><att name="EDGE_LABEL_WIDTH" value="200.0" type="string" cy:type="String"/><att name="EDGE_CURVED" value="true" type="string" cy:type="String"/><att name="EDGE_SOURCE_ARROW_SIZE" value="6.0" type="string" cy:type="String"/><att name="EDGE_VISIBLE" value="true" type="string" cy:type="String"/><att name="EDGE_LINE_TYPE" value="SOLID" type="string" cy:type="String"/><att name="EDGE_STROKE_SELECTED_PAINT" value="#FF0000" type="string" cy:type="String"/><att name="EDGE_LABEL_FONT_SIZE" value="10" type="string" cy:type="String"/><att name="EDGE_LABEL_FONT_FACE" value="Dialog.plain,plain,10" type="string" cy:type="String"/><att name="EDGE_Z_ORDER" value="0.0" type="string" cy:type="String"/><att name="EDGE_SOURCE_ARROW_SELECTED_PAINT" value="#FFFF00" type="string" cy:type="String"/></graphics></edge>'
        in_edge = in_edge + temp_edge

#xgmml node format
in_node = ''
for node_str in show_node:
    temp_node = ''
    if(len(node_str.split('\t')) < 2):
        print(node_str)
    cla_name, name_id = node_str.split('\t')
    cla, name = cla_name.split('$')
    #print(name)
    if('&' in name):
        name = name.replace('&', ' and ')
    if('"' in name):
        name = name.replace('"', '')
    if(cla == 'Chemical'):
        shape = 'ELLIPSE'
        fill = '#67A9CF'
    elif(cla == 'Gene'):
        shape = 'TRIANGLE'
        fill = '#74C476'
    elif(cla == 'Species'):
        shape = 'DIAMOND'
        fill = '#FD8D3C'
    elif(cla == 'Disease'):
        shape = 'ROUND_RECTANGLE'
        fill = '#8C96C6'
    elif(cla == 'Mutation'):
        shape = 'PARALLELOGRAM'
        fill = '#FCCDE5'
    elif(cla == 'CellLine'):
        shape = 'VEE'
        fill = '#BDBDBD'
    elif(re.search('custom_', cla)):
        shape = 'HEXAGON'
        fill = '#FA9FB5'
    else:
        #print(cla)
        shape = 'OCTAGON'
        fill = '#FFFFB3'
        
    temp_node = '<node id="'+ str(node_dict[cla_name]) +'" label="'+ name +'"><att name="shared name" value="'+ name +'" type="string" cy:type="String"/><att name="name" value="'+ name +'" type="string" cy:type="String"/><att name="class" value="'+ cla +'" type="string" cy:type="String"/><graphics width="0.0" h="35.0" w="35.0" z="0.0" type="'+ shape +'" outline="#CCCCCC" fill="'+ fill +'"><att name="NODE_SELECTED" value="false" type="string" cy:type="String"/><att name="NODE_NESTED_NETWORK_IMAGE_VISIBLE" value="true" type="string" cy:type="String"/><att name="NODE_DEPTH" value="0.0" type="string" cy:type="String"/><att name="NODE_SELECTED_PAINT" value="#FFFF00" type="string" cy:type="String"/><att name="NODE_LABEL_ROTATION" value="0.0" type="string" cy:type="String"/><att name="NODE_LABEL_WIDTH" value="200.0" type="string" cy:type="String"/><att name="COMPOUND_NODE_PADDING" value="10.0" type="string" cy:type="String"/><att name="NODE_LABEL_TRANSPARENCY" value="255" type="string" cy:type="String"/><att name="NODE_LABEL_POSITION" value="C,C,c,0.00,0.00" type="string" cy:type="String"/><att name="NODE_LABEL" value="'+ name +'" type="string" cy:type="String"/><att name="NODE_VISIBLE" value="true" type="string" cy:type="String"/><att name="NODE_LABEL_FONT_SIZE" value="12" type="string" cy:type="String"/><att name="NODE_BORDER_STROKE" value="SOLID" type="string" cy:type="String"/><att name="NODE_LABEL_FONT_FACE" value="SansSerif.plain,plain,12" type="string" cy:type="String"/><att name="NODE_BORDER_TRANSPARENCY" value="255" type="string" cy:type="String"/><att name="COMPOUND_NODE_SHAPE" value="ROUND_RECTANGLE" type="string" cy:type="String"/><att name="NODE_LABEL_COLOR" value="#000000" type="string" cy:type="String"/><att name="NODE_TRANSPARENCY" value="255" type="string" cy:type="String"/></graphics></node>'
    in_node = in_node + temp_node

start_graph = '<graph id="1" label="'+ file_name +'n" directed="1" cy:documentVersion="3.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:cy="http://www.cytoscape.org" xmlns="http://www.cs.rpi.edu/XGMML">'
end_graph = '</graph>'

print('Show node count:' + str(len(show_node)))
print('Show edge count:' + str(edge_count))

#Write xgmml file
with open(file_name + '(weight_' + cut_weight + ').xgmml', 'w') as pubtator_xgmml:
    pubtator_xgmml.write(title + start_graph + in_graphics + in_node + in_edge + end_graph)