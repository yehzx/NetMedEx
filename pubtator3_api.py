# https://www.ncbi.nlm.nih.gov/research/pubtator3/api
import argparse
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Literal

import requests
from tqdm.auto import tqdm

# pmid batch_size
BATCH_SIZE = 100


def run_query_pipeline(query, savepath, type: Literal["query", "pmids"], name):
    if type == "query":
        article_dict = get_search_results(query)
        output = obtain_article_annotations(article_dict)
        output_path = savepath / f"{query}.pubtator" if name is None else savepath / f"{name}.pubtator"
        write_output(output, savepath=output_path)
    elif type == "pmids":
        output = batch_publication_query(query, type="pmids")
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        output_path = savepath / f"result_{now}.pubtator" if name is None else savepath / f"{name}.pubtator"
        write_output(output, savepath=output_path)


def get_search_results(query, max_articles=1000):
    print(f"Query: {query}")
    res = send_search_query(query)
    res_json = res.json()
    total_articles = int(res_json["count"])
    total_pages = int(res_json["total_pages"])
    page_size = int(res_json["page_size"])

    print(f"Get {total_articles} articles")
    n_articles_to_request = max_articles if total_articles > max_articles else total_articles
    print(f"Requesting {n_articles_to_request} articles...")

    article_dict = OrderedDict()
    if request_successful(res):
        article_dict.update(get_article_ids(res_json))

    # Get search results in different pages until the max_articles is reached
    current_page = 1
    with tqdm(total=n_articles_to_request) as pbar:
        while current_page * page_size < n_articles_to_request:
            pbar.update(page_size)
            current_page += 1
            res = send_search_query_with_page(query, current_page)
            if request_successful(res):
                article_dict.update(get_article_ids(res.json()))
        pbar.n = pbar.total

    while len(article_dict) > max_articles:
        _ = article_dict.popitem()

    return article_dict


def send_search_query(query):
    search_url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    res = requests.get(search_url, params={"text": query})
    time.sleep(0.5)
    return res


def send_search_query_with_page(query, page):
    search_url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/search/"
    res = requests.get(search_url, params={"text": query,
                                           "sort": "score desc",
                                           "page": page})
    time.sleep(0.5)
    return res


def request_successful(res):
    if res.status_code != 200:
        print("Unsuccessful request")
        return False
    return True


def get_article_ids(res_json):
    article_dict = {}
    for article in res_json["results"]:
        article_id = article["_id"]
        article_dict[article_id] = {}
        # Get pmid
        article_dict[article_id]["pmid"] = article.get("pmid")
        # Get pmcid
        article_dict[article_id]["pmcid"] = article.get("pmcid")

    return article_dict


def obtain_article_annotations(article_dict, full_text=False):
    output = []
    print("Obtaining article annotations...")
    if full_text:
        pass
    else:
        to_query_pmids = []
        for article in article_dict.values():
            to_query_pmids.append(str(article["pmid"]))

        output = batch_publication_query(to_query_pmids, type="pmids")

    return output


def batch_publication_query(id_list, type, batch_size=BATCH_SIZE, format="pubtator"):
    output = []
    with tqdm(total=len(id_list)) as pbar:
        for start in range(0, len(id_list), batch_size):
            end = start + batch_size 
            end = end if end < len(id_list) else None
            res = send_publication_query(
                ",".join(id_list[start:end]), type=type, format=format)
            if request_successful(res):
                output.append(res.text)
            if end is not None: 
                pbar.update(batch_size)
            else:
                pbar.n = len(id_list)

    return output


def send_publication_query(article_id, type, format="pubtator"):
    pub_url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/{format}"
    res = requests.get(pub_url, params={type: article_id})
    time.sleep(0.5)
    return res


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
    args = parser.parse_args()

    output_dir = Path(args.output)
    if not output_dir.is_dir():
        raise Exception(f"{output_dir} is not a directory")

    if args.query is not None:
        run_query_pipeline(args.query, output_dir, "query", args.name)
    elif args.pmids is not None:
        pmids = args.pmids.split(",")
        pmids = drop_if_not_num(pmids)
        print(f"Find {len(pmids)} PMIDs")
        run_query_pipeline(pmids, output_dir, "pmids", args.name)
    elif args.pmid_file is not None:
        pmids = load_pmids(args.pmid_file)
        run_query_pipeline(pmids, output_dir, "pmids", args.name)
