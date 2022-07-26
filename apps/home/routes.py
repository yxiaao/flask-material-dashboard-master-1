# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""
import json

from apps.home import blueprint
from flask import render_template, request
from flask_login import login_required
from jinja2 import TemplateNotFound
from docx import Document
import jsonlines

# Entity_link model
import en_core_web_lg
# Contract Review model
from legal_annotator.annotator import Annotator
# Similarity model
# import ast
# from retrieval_code_master.retrieval_demo_class import Retriever

# Load Models
# Entity Link
nlp = en_core_web_lg.load()
nlp.add_pipe('dbpedia_spotlight')
document_Data = {}
has_processed = 'false'
# Contract Review
LM_checkpoint_path = 'legal_annotator/roberta-base'
anno_info_path = 'legal_annotator/CUAD_anno_info.txt'
anno = Annotator(LM_checkpoint_path=LM_checkpoint_path, anno_info_path=anno_info_path)
# Similarity
# model = Retriever()


@blueprint.route('/index')
@login_required
def index():
    return render_template('home/index.html', segment='index', document_selected='false', processed='false')


@blueprint.route('/process_document', methods=['GET', 'POST'])
@login_required
def processFile():
    if request.method == 'POST':
        print(request.form)
        global document_Data
        # result = handleContract(request.form['content'])
        global has_processed
        document_Data['result'] = handleContract(request.form['content'])
        has_processed = 'true'
        document_Data['content'] = request.form['content']
        return render_template("home/entityLink.html", segment='entityLink', document_selected='true',
                               processed=has_processed, documentData=document_Data)


@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def handleFile():
    if request.method == 'POST':
        global document_Data
        global has_processed
        f = request.files['input_file']
        print(request.files)
        f.save('./apps/upload/' + f.filename)
        document = Document('./apps/upload/' + f.filename)
        document_Data['input_name'] = (f.filename.split('.'))[0]
        if not document_Data.__contains__('content'):
            document_Data['content'] = ''

        for paragraph in document.paragraphs:
            document_Data['content'] += (paragraph.text + '\n')
    return render_template('home/document.html', segment='document', document_selected='true', processed='false',
                           documentData=document_Data)


@blueprint.route('/kg')
@login_required
def handle_kg():
    return render_template('home/main_kg4.html')


@blueprint.route('/<template>')
@login_required
def route_template(template):
    try:

        if not template.endswith('.html'):
            template += '.html'

        # Detect the current page
        segment = get_segment(request)
        global document_Data
        global has_processed
        for key in request.args:
            document_Data[key] = request.args.get(key)
        if template == "similarity.html":
            document_selected = 'false'
            has_processed = 'false'
        else:
            document_selected = 'true'
        # Serve the file (if exists) from app/templates/home/FILE.html
        return render_template("home/" + template, segment=segment, document_selected=document_selected,
                               processed=has_processed, documentData=document_Data)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except:
        return render_template('home/page-500.html'), 500


# Helper - Extract current page name from request
def get_segment(request):
    try:

        segment = request.path.split('/')[-1]

        if segment == '':
            segment = 'index'

        return segment

    except:
        return None


def handleContract(content):
    processResult = {}
    processResult['EntityLink'] = handleEntityLink(content)
    processResult['Summarize'] = handleSummarize(content)
    processResult['Review'] = handleReview(content)
    # processResult['KnowledgeGraph'] = handleKnowledgeGraph(content)
    # processResult['Similarity'] = handleSimilarity(content)
    return processResult


def handleReview(content):
    review = []
    with jsonlines.open('./apps/static/result/review/output.jsonl', mode='r') as reader:
        for row in reader:
            review.append(row)
    text = content

    result = anno(text)
    # output = convert_html_element(text, result) + convert_html_element_table(result)
    return result


def handleSummarize(content):
    paragraph = []
    summarized = []
    with jsonlines.open('./apps/static/result/paragraph_summarization/outputs.jsonl', mode='r') as reader:
        for row in reader:
            summarized.append(row)
    with jsonlines.open('./apps/static/result/paragraph_summarization/inputs.jsonl', mode='r') as reader:
        for row in reader:
            paragraph.append(row)
    return {'para': paragraph, 'sum': summarized}


def handleSimilarity(content):
    if content['retrieved_function'] == "similar":
        sentence_list = []
        text = request.form['text']
        sentence_list.append(text)
        neighbor_str_list, neighbor_score_list = model.get_ann_sent_recommend(sentence_list)
        print(neighbor_str_list)
        print(neighbor_score_list)
        if type(neighbor_str_list) == str:
            result_html = neighbor_str_list
        else:
            result_html = convert_html_retrieve_table(neighbor_str_list, neighbor_score_list)
        print(result_html)

        return render_template("Contract_similarity.html", original_input=text, result=result_html)

    if content['retrieved_function'] == "supplementary":

        # sentence_list =[]
        text = content['text']
        sentence_list = ast.literal_eval(text)
        neighbor_str_list = model.get_supplementary_sent(sentence_list)
        print(neighbor_str_list)
        if type(neighbor_str_list) == str:
            result_html = neighbor_str_list
        else:
            result_html = convert_html_supple_table(neighbor_str_list)
        print(result_html)
        return render_template("Contract_similarity.html", original_input=text, result=result_html)


def handleEntityLink(content):
    doc = nlp(content)
    # pre_result = convert_html(doc)
    linkInfo = doc.to_json()['spans']['dbpedia_spotlight']
    # {start, end, label, kb_id}
    print(linkInfo)
    return linkInfo

    # return pre_result


def convert_html(doc, result):
    last_idx = 0
    children = []
    for ent in doc.ents:
        if ent.kb_id_ != '':
            children.append(doc.text[last_idx:ent.start_char])
            children.append(
                entity(doc.text[ent.start_char:ent.end_char], ent.kb_id_))
            last_idx = ent.end_char
            if ent == doc.ents[-1]:
                children.append(doc.text[last_idx:])

    return ' '.join(children)


def entity(entity_text, entity_link):
    linking_html = "<span class = 'highlight' url=" + '"' + entity_link + '"' + ' target="_blank">' + entity_text + "</span>"
    return linking_html


### Retrieve task
def convert_html_retrieve_table(result, score):
    output = []
    contract_elem_start = '<table>\n<caption> Similar Contract Retrieved </caption>\n<thead>\n<tr>\n<th scope="col">Score</th>\n<th scope="col"> Retrieved Contract Sentence </th>\n</tr>\n</thead>\n<tbody>\n'
    contract_elem_last = '</tbody>\n</table>'
    output.append(contract_elem_start)
    for i in range(len(result[0])):
        output.append(table_retrieve(result[0][i], score[0][i]))
    output.append(contract_elem_last)
    return ''.join(output)


def table_retrieve(sent, score):
    sentence_html = '<tr>\n<th scope="row">' + str(round(score, 2)) + '</th>\n<td>' + sent + '</td>\n</tr>\n'
    return sentence_html


### supplementary task
def convert_html_supple_table(result):
    output = []
    contract_elem_start = '<table>\n<caption> Supplementary Contract Retrieved </caption>\n<thead>\n<tr>\n<th scope="col"> Supplementary Contract Sentence </th>\n</tr>\n</thead>\n<tbody>\n'
    contract_elem_last = '</tbody>\n</table>'
    output.append(contract_elem_start)
    for supp_sent in result:
        output.append(table_supple(supp_sent))
    output.append(contract_elem_last)
    return ''.join(output)


def table_supple(sent):
    sentence_html = '<tr>\n<td>' + sent + '</td>\n</tr>\n'
    return sentence_html





