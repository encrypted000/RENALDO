from dash import html


def create_header():
    return html.Div([
        html.Div([
            html.Div([
                html.Div("R", className="logo-badge"),
                html.Div([
                    html.H1("RENALDO"),
                    html.Div(
                        "RarE kidNey dAta compLeteness DashbOard · UK Kidney Association",
                        className="header-sub",
                    ),
                ]),
            ], className="header-logo"),

            html.Div([
                html.Div(id="last-updated", children="Loading...",
                         className="header-date"),
                html.Div("Last refreshed", className="header-label"),
                html.Div([
                    html.Div(className="live-dot"),
                    html.Span(id="total-patients-hdr", children="—"),
                    html.Span(" active patients"),
                ], className="header-patients"),
            ], className="header-meta"),

        ], className="header-inner"),

        html.Div([
            html.Div([
                html.Div([
                    html.Button("Expand all",     className="nav-btn", id="expand-btn"),
                    html.Button("Collapse all",   className="nav-btn", id="collapse-btn"),
                    html.Button("↻ Refresh data", className="nav-btn accent", id="refresh-btn"),
                ], className="nav-actions"),
            ], className="nav-inner"),
        ], className="nav-strip"),

    ], className="header")