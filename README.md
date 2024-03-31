## PubTator3 API scripts

### Usage
```
usage: pubtator3_api.py [-h] [-q QUERY] [-o OUTPUT] [-p PMIDS] [-f PMID_FILE] [--max_articles MAX_ARTICLES] [--full_text] [--standardized_name]

optional arguments:
  -h, --help            show this help message and exit
  -q QUERY, --query QUERY
                        Query string
  -o OUTPUT, --output OUTPUT
                        Output path
  -p PMIDS, --pmids PMIDS
                        PMIDs for the articles (comma-separated)
  -f PMID_FILE, --pmid_file PMID_FILE
                        Filepath to load PMIDs
  --max_articles MAX_ARTICLES
                        Maximal articles to request from the searching result (default: 1000)
  --full_text           Get full-text annotations
  --standardized_name   Obtain standardized names rather than the original text in articles
```

### Examples

**Query with keywords**
```
# Basic 
python pubtator3_api.py -q "N-dimethylnitrosamine and Metformin" [-o OUTPUT_FILEPATH]

# Advanced
python pubtator3_api.py -q "@DISEASE_COVID_19 AND @GENE_PON1" [-o OUTPUT_FILEPATH]
```

**Query with PMIDs**
```
python pubtator3_api.py -p 34895069,35883435,34205807 [-o OUTPUT_FILEPATH]
```

**Load PMIDs from file**
```
python pubtator3_api.py -f examples/example_input.txt [-o OUTPUT_FILEPATH]
```

**Streamline with pubtator2cytoscape (new version)**
```
python pubtator3_api.py -q "@DISEASE_COVID_19 AND @GENE_PON1" -o examples/example_output.pubtator --standardized_name
python pubtator2cytoscape.py -i examples/example_output.pubtator -o examples/example_output.xgmml -w 5
```

**Streamline with pubtator2cytoscape (previous version)**
```
python pubtator3_api.py -q "@DISEASE_COVID_19 AND @GENE_PON1" -o examples/example_output.pubtator
python pubtator2cytoscape_v6.py -i examples/example_output.pubtator -w 5
```
