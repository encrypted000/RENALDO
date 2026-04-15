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

    return app
