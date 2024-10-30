import logging
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from netmedex.api_cli import main, write_output
from netmedex.network_cli import pubtator2cytoscape

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(scope="module")
def tempdir():
    with TemporaryDirectory() as tempdir:
        yield Path(tempdir)


@pytest.fixture(scope="module")
def paths(request):
    test_dir = Path(request.config.rootdir) / "tests/test_data"
    return {
        "simple": test_dir / "6_nodes_3_clusters_mesh.pubtator"
    }


@pytest.fixture(scope="module")
def tocytoscape_cli_args():
    args = {
        "cut_weight": 1,
        "format": "html",
        "node_type": "all",
        "weighting_method": "freq",
        "pmid_weight": None,
        "community": False,
    }
    return {
        "args_basic": args,
        "args_community": {**args, "community": True},
        "args_mesh_only": {**args, "node_type": "mesh"},
        "args_relation_only": {**args, "node_type": "relation"},
        "args_npmi": {**args, "weighting_method": "npmi"},
        "args_weight": {**args, "cut_weight": 20},
        "args_xgmml": {**args, "format": "xgmml"},
    }


@pytest.mark.parametrize("query,error_message", [
    ("", "Your search cannot be empty."),
    ("qtihasiogha", "No articles found by PubTator3 API."),
    ("covid19", "Possibly too many articles. Please try more specific queries."),
])
def test_api_pubtator3_api_end_to_end(query, error_message, tempdir):
    p = subprocess.run(
        [
            "pubtator3",
            "-q",
            query,
            "-o",
            tempdir / "test.pubtator",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    last_message = p.stdout.strip().split("\n")[-1]

    assert last_message == error_message, f"Expected message '{error_message}', but got '{last_message}'"


@pytest.mark.parametrize("args,expected", [
    (["api.py", "-q", "foo", "-o", "bar", "--max_articles", "100", "--full_text"],
     {"query": "foo", "savepath": Path("bar"), "type": "query", "max_articles": 100, "full_text": True, "use_mesh": False}),
    (["api.py", "-q", "foo", "-o", "bar", "--max_articles", "100", "--use_mesh"],
     {"query": "foo", "savepath": Path("bar"), "type": "query", "max_articles": 100, "full_text": False, "use_mesh": True}),
    (["api.py", "-q", "foo"],
     {"query": "foo", "savepath": Path("query_foo.pubtator"), "type": "query", "max_articles": 1000, "full_text": False, "use_mesh": False}),
    (["api.py", "-p", "123,456", "-o", "bar"],
     {"query": ["123", "456"], "savepath": Path("bar"), "type": "pmids", "max_articles": 1000, "full_text": False, "use_mesh": False}),
    (["api.py", "-p", "123,456", "--full_text"],
     {"query": ["123", "456"], "savepath": Path("pmids_123_total_2.pubtator"), "type": "pmids", "max_articles": 1000, "full_text": True, "use_mesh": False}),
    (["api.py", "-f", "./tests/test_data/pmid_list.txt", "--max_articles", "10000"],
     {"query": ["34205807", "34895069", "35883435"], "savepath": Path("pmids_34205807_total_3.pubtator"), "type": "pmids", "max_articles": 10000, "full_text": False, "use_mesh": False}),
])
def test_pubtator3_api_main(args, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with mock.patch("netmedex.api_cli.run_query_pipeline") as mock_pipeline:
        main()
        mock_pipeline.assert_called_once_with(query=expected["query"],
                                              savepath=expected["savepath"],
                                              type=expected["type"],
                                              max_articles=expected["max_articles"],
                                              full_text=expected["full_text"],
                                              use_mesh=expected["use_mesh"])


@pytest.mark.parametrize("args", [
    ["api.py", "-q", ""],
    ["api.py", "-p", "  "],
])
def test_pubtator3_api_exceptions(args, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with mock.patch("netmedex.api_cli.logger") as mock_logger:
        main()
        mock_logger.error.assert_called_once()


@pytest.mark.parametrize("args", [
    ["api.py", "-p", "123", "-q", "bar"],
    ["api.py", "-f", "foo.txt", "-q", "bar"],
])
def test_pubtator3_api_exit(args, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit):
        with mock.patch("netmedex.api_cli.logger") as mock_logger:
            main()
            mock_logger.info.assert_called_once()


def test_write_output_none():
    open_mock = mock.mock_open()
    with mock.patch("builtins.open", create=True):
        write_output("foo", None, False)
        open_mock.assert_not_called()


@pytest.mark.parametrize("output,savepath,use_mesh,expected", [
    ("foo", "bar.pubtator", False, "foo"),
    ("foo", "bar.pubtator", True, "foo")
])
def test_write_output(output, savepath, use_mesh, expected):
    open_mock = mock.mock_open()
    with mock.patch("builtins.open", open_mock, create=True), \
            mock.patch("netmedex.api_cli.logger") as mock_logger:
        write_output(output, savepath, use_mesh)
        if use_mesh:
            open_mock.return_value.writelines.assert_any_call(
                ["##USE-MESH-VOCABULARY", "\n"])
        open_mock.return_value.writelines.assert_any_call(output)
        mock_logger.info.assert_called_with(f"Save to {savepath}")


@pytest.mark.parametrize("args", [
    "args_basic",
    "args_community",
    "args_mesh_only",
    "args_relation_only",
    "args_npmi",
    "args_weight",
    "args_xgmml",
])
def test_tocytoscape_cli(args, paths, tempdir, tocytoscape_cli_args):
    savepath = tempdir / "tests.out"
    pubtator2cytoscape(paths["simple"], savepath, tocytoscape_cli_args[args])
