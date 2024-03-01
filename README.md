## PubTator3 API scripts

### Usage
```
usage: pubtator3_api.py [-h] [-q QUERY] [-o OUTPUT] [-n NAME] [-p PMIDS] [-f PMID_FILE] [--max_articles MAX_ARTICLES]

optional arguments:
  -h, --help            show this help message and exit
  -q QUERY, --query QUERY
                        Query string
  -o OUTPUT, --output OUTPUT
                        Output directory (default: ./)
  -n NAME, --name NAME  Filename
  -p PMIDS, --pmids PMIDS
                        PMIDs for the articles (comma-separated)
  -f PMID_FILE, --pmid_file PMID_FILE
                        Filepath to load PMIDs
  --max_articles MAX_ARTICLES
                        Maximal articles to request from the searching result (default: 1000)
```

### Examples

**Query with keywords**
```
# Basic 
python pubtator3_api.py -q "N-dimethylnitrosamine and Metformin" [-o OUTPUT_DIR] [-n FILENAME]

# Advanced
python pubtator3_api.py -q "@DISEASE_COVID_19 AND @GENE_PON1" [-o OUTPUT_DIR] [-n FILENAME]
```

**Query with PMIDs**
```
python pubtator3_api.py -p 34895069,35883435,34205807 [-o OUTPUT_DIR] [-n FILENAME]
```

**Load PMIDs from file**
```
python pubtator3_api.py -f examples/example_input.txt [-o OUTPUT_DIR] [-n FILENAME]
```

**Pipeline with pubtator2cytoscape**
```
python pubtator3_api.py -q "@DISEASE_COVID_19 AND @GENE_PON1" -n examples/example_output
python pubtator2cytoscape_v6.py -i examples/example_output.pubtator -w 5
```
