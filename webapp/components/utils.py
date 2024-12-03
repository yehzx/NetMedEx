import dash
from dash import html


def generate_param_title(title, descriptions):
    return html.Div(
        [
            html.H5(title),
            html.Span(
                [
                    html.Img(src=dash.get_asset_url("icon_info.svg"), className="info-img"),
                    html.Div(
                        descriptions,
                        className="info-inner",
                    ),
                ],
                className="info-outer",
            ),
        ],
        className="param-title",
    )
