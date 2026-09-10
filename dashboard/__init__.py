import dash
import dash_bootstrap_components as dbc
from dashboard.layout import create_layout


def create_app():
    """Create and configure the Dash application."""
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title="RENALDO",
        suppress_callback_exceptions=True,
    )

    app.layout = create_layout()

    # Register callbacks (must be imported after app is created)
    from dashboard.callbacks import data_callbacks, render_callbacks  # noqa: F401

    @app.server.after_request
    def set_security_headers(response):
        # Conservative headers that can't break Dash's inline scripts/styles —
        # no CSP here, since getting that wrong would silently break the app
        # and there's no browser to verify it in from this environment.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    return app
