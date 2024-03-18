# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
import argparse
import json
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Literal

import requests
from tqdm.auto import tqdm

# API GET limit: 100
PMID_REQUEST_SIZE = 100
QUERY_METHOD = ["search", "cite"][1]
# Full text annotation is only availabe in `biocxml` and `biocjson` formats
# RESPONSE_FORMAT = ["pubtator", "biocxml", "biocjson"][2]


def run_query_pipeline(query, savepath, type: Literal["query", "pmids"],
                       name, max_articles=1000, full_text=False,
                       standardized=False):
    if type == "query":
        pmid_list = get_search_results(query, max_articles)
        if name is None:
            output_path = savepath / f"{query}.pubtator"
        else:
            output_path = savepath / f"{name}.pubtator"
    elif type == "pmids":
        pmid_list = query
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        if name is None:
            output_path = savepath / f"result_{now}.pubtator"
        else:
            output_path = savepath / f"{name}.pubtator"
        
    output = batch_publication_query(pmid_list, type="pmids",
                                     full_text=full_text,
                                     standardized=standardized)
    if standardized:
        output = [convert_to_pubtator(i, retain_ori_text=False, role_type="name") for i in output]
    elif full_text:
        output = [convert_to_pubtator(i, retain_ori_text=True, role_type="name") for i in output]

    write_output(output, savepath=output_path)


def get_search_results(query, max_articles):
    print(f"Query: {query}")
    if QUERY_METHOD == "search":
        article_list = get_by_search(query, max_articles)
    elif QUERY_METHOD == "cite":
        article_list = get_by_cite(query, max_articles)

    return article_list


def get_by_search(query, max_articles):
    res = send_search_query(query, type="search")

    article_list = []
    if not request_successful(res):
        return article_list

    res_json = res.json()
    total_articles = int(res_json["count"])
    page_size = int(res_json["page_size"])
    article_list.extend(get_article_ids(res_json))

    n_articles_to_request = get_n_articles(max_articles, total_articles)

    # Get search results in different pages until the max_articles is reached
    current_page = 1
    with requests.Session() as session:
        with tqdm(total=n_articles_to_request) as pbar:
            while current_page * page_size < n_articles_to_request:
                pbar.update(page_size)
                current_page += 1
                res = send_search_query_with_page(query, current_page, session)
                if request_successful(res):
                    article_list.extend(get_article_ids(res.json()))
            pbar.n = pbar.total

    return article_list[:n_articles_to_request]


def get_n_articles(max_articles, total_articles):
    print(f"Get {total_articles} articles")
    n_articles_to_request = max_articles if total_articles > max_articles else total_articles
    print(f"Requesting {n_articles_to_request} articles...")
    return n_articles_to_request


def get_by_cite(query, max_articles):
    res = send_search_query(query, type="cite")
    if not request_successful(res):
        return OrderedDict()

    pmid_list = parse_cite_response(res.text)
    n_articles_to_request = get_n_articles(max_articles, len(pmid_list))

    return pmid_list[:n_articles_to_request]


def parse_cite_response(res_text):
    pmid_list = []
    for line in res_text.split("\n"):
        if line.startswith("#") or line == "":
            continue
        # [pmid, title, journal]
        pmid = line.split("\t")[0]
        pmid_list.append(pmid)
    return pmid_list


def send_search_query(query, type: Literal["search", "cite"] = QUERY_METHOD):
    if type == "search":
        search_url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    elif type == "cite":
        search_url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/cite/tsv"
    res = requests.get(search_url, params={"text": query})
    time.sleep(0.5)
    return res


def send_search_query_with_page(query, page, session=None):
    search_url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    params = {"text": query,"sort": "score desc", "page": page}
    if session is None:
        res = requests.get(search_url, params=params)
    else:
        res = session.get(search_url, params=params)
    time.sleep(0.5)
    return res


def request_successful(res):
    if res.status_code != 200:
        print("Unsuccessful request")
        return False
    return True


def get_article_ids(res_json):
    return [str(article.get("pmid")) for article in res_json["results"]]


def batch_publication_query(id_list, type, full_text=False, standardized=False):
    output = []
    format = "biocjson" if standardized or full_text else "pubtator"
    with requests.Session() as session:
        with tqdm(total=len(id_list)) as pbar:
            for start in range(0, len(id_list), PMID_REQUEST_SIZE):
                end = start + PMID_REQUEST_SIZE
                end = end if end < len(id_list) else None
                res = send_publication_query(
                    ",".join(id_list[start:end]),
                    type=type, format=format, full_text=full_text,
                    session=session)
                if request_successful(res):
                    output.extend(append_json_or_text(res, full_text, standardized))
                if end is not None:
                    pbar.update(PMID_REQUEST_SIZE)
                else:
                    pbar.n = len(id_list)

    return output


def send_publication_query(article_id, type: Literal["pmids", "pmcids"], format,
                           full_text=False, session=None):
    pub_url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{format}"
    params = {type: article_id}
    if full_text:
        params["full"] = "true"
    if session is None:
        res = requests.get(pub_url, params=params)
    else:
        res = session.get(pub_url, params=params)
    time.sleep(0.5)
    return res


def append_json_or_text(res, full_text, standardized):
    if full_text or standardized:
        if len(res.text.split("\n")) > 2:
            content = [json.loads(text) for text in res.text.split("\n")[:-1]]
        else:
            content = [res.json()]
    else:
        content = [res.text]

    return content


def convert_to_pubtator(res_json, retain_ori_text=True, role_type: Literal["identifier", "name"] = "identifier"):
    pmid = res_json["pmid"]
    title = res_json["passages"][0]["text"]
    annotation_list = get_biocjson_annotations(res_json, retain_ori_text)
    relation_list = get_biocjson_relations(res_json, role_type)
    converted_str = create_pubtator_str(pmid, title, annotation_list, relation_list)

    return converted_str


def create_pubtator_str(pmid, title, annotation_list, relation_list):
    title_str = f"{pmid}|t|{title}\n"
    annotation_str = [(f"{pmid}\t"
                       f"{annotation['locations']['offset']}\t"
                       f"{annotation['locations']['length'] + annotation['locations']['offset']}\t"
                       f"{annotation['name']}\t"
                       f"{annotation['type']}\t"
                       f"{annotation['id']}")
                      for annotation in annotation_list]
    relation_str = [(f"{pmid}\t"
                     f"{relation['type']}\t"
                     f"{relation['role1']}\t"
                     f"{relation['role2']}")
                    for relation in relation_list]

    return title_str + "\n".join(annotation_str) + "\n" + "\n".join(relation_str) + "\n\n"


def get_biocjson_annotations(res_json, retain_ori_text):
    n_passages = len(res_json["passages"])
    passages_type = [res_json["passages"][i]["infons"]["type"]
                     for i in range(n_passages)]
    annotation_list = []
    # TODO: extract from specific passages only?
    for annotation_entries in [res_json["passages"][i]["annotations"] for i in range(n_passages)]:
        for annotation_entry in annotation_entries:
            each_annotation = {}
            id = annotation_entry["infons"]["normalized_id"]
            each_annotation["id"] = "-" if id == "None" or id is None else id
            each_annotation["type"] = annotation_entry["infons"]["type"]
            each_annotation["locations"] = annotation_entry["locations"][0]
            
            if each_annotation["type"] in ("Disease", "Chemical"):
                if each_annotation["id"] != "-":
                    each_annotation["id"] = f"MESH:{id}"

            # In type == "species", the entity name is stored in "text"
            if each_annotation["type"] == "Species":
                each_annotation["name"] = annotation_entry["text"]
            else:
                # Whether to keep the standardized MeSH term or the
                # text in articles
                # If retain_ori_text, keep the original text
                if retain_ori_text:
                    each_annotation["name"] = annotation_entry["text"]
                else:
                    try:
                        each_annotation["name"] = annotation_entry["infons"]["name"]
                    except KeyError:
                        each_annotation["name"] = annotation_entry["text"]
            annotation_list.append(each_annotation)

    return annotation_list


def get_biocjson_relations(res_json, role_type):
    n_relations = len(res_json["relations"])
    relation_list = []
    for relation_entry in res_json["relations"]:
        each_relation = {}
        each_relation["role1"] = relation_entry["infons"]["role1"][role_type]
        each_relation["role2"] = relation_entry["infons"]["role2"][role_type]
        each_relation["type"] = relation_entry["infons"]["type"]
        relation_list.append(each_relation)

    return relation_list


def write_output(output, savepath: Path):
    with open(savepath, "w") as f:
        f.writelines(output)
        print(f"Save to {str(savepath)}")


def load_pmids(filepath):
    print(f"Load PMIDs from: {filepath}")
    with open(filepath) as f:
        pmids = []
        for line in f.readlines():
            pmids.extend(line.strip().split(","))

    pmids = drop_if_not_num(pmids)

    print(f"Find {len(pmids)} PMIDs")

    return pmids


def drop_if_not_num(id_list):
    checked_list = []
    for id in id_list:
        try:
            _ = int(id)
            checked_list.append(id)
        except ValueError:
            pass

    return checked_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--query", default=None,
                        help="Query string")
    parser.add_argument("-o", "--output", default="./",
                        help="Output directory (default: ./)")
    parser.add_argument("-n", "--name", default=None,
                        help="Filename")
    parser.add_argument("-p", "--pmids", default=None, type=str,
                        help="PMIDs for the articles (comma-separated)")
    parser.add_argument("-f", "--pmid_file", default=None,
                        help="Filepath to load PMIDs")
    parser.add_argument("--max_articles", type=int, default=1000,
                        help="Maximal articles to request from the searching result (default: 1000)")
    parser.add_argument("--full_text", action="store_true",
                        help="Get full-text annotations")
    parser.add_argument("--standardized_name", action="store_true",
                        help="Obtain standardized names rather than the original text in articles")
    args = parser.parse_args()

    output_dir = Path(args.output)
    if not output_dir.is_dir():
        raise Exception(f"{output_dir} is not a directory")

    if args.query is not None:
        run_query_pipeline(query=args.query,
                           savepath=output_dir,
                           type="query",
                           name=args.name,
                           max_articles=args.max_articles,
                           full_text=args.full_text,
                           standardized=args.standardized_name)
        sys.exit()
    elif args.pmids is not None:
        pmids = args.pmids.split(",")
        pmids = drop_if_not_num(pmids)
        print(f"Find {len(pmids)} PMIDs")
    elif args.pmid_file is not None:
        pmids = load_pmids(args.pmid_file)

    run_query_pipeline(query=pmids,
                       savepath=output_dir,
                       type="pmids",
                       name=args.name,
                       max_articles=args.max_articles,
                       full_text=args.full_text,
                       standardized=args.standardized_name)
