from dash import html


def create_header():
    return html.Div([
        html.Div([
            html.Div([
                html.Img(src="/assets/logo.png", className="logo-badge"),
                html.Div([
                    html.H1("RENALDO"),
                    html.Div("RarE kidNey dAta compLeteness DashbOard · UK Kidney Association", className="header-sub"),
                ]),
            ], className="header-logo"),

            html.Div([
                html.Div([
                    html.Span(id="total-patients-hdr", children="—", className="header-stat-value"),
                    html.Span(" total participants", className="header-stat-label"),
                ], className="header-stat"),
                html.Div([
                    html.Div(className="live-dot"),
                    html.Span("Updated "),
                    html.Span(id="last-updated", children="Loading..."),
                ], className="header-updated"),
            ], className="header-meta"),

        ], className="header-inner"),

        html.Div([
            html.Div([
                html.Div([
                    html.Button("Expand all",   className="nav-btn", id="expand-btn"),
                    html.Button("Collapse all", className="nav-btn", id="collapse-btn"),
                    html.Button("Refresh data", className="nav-btn accent", id="refresh-btn"),
                ], className="nav-actions"),
            ], className="nav-inner"),
        ], className="nav-strip"),

    ], className="header")