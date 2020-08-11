from copy import copy
import json
from pathlib import Path

from IPython.display import HTML
import pandas as pd
import responses

from bbsearch.widgets import MiningWidget, ArticleSaver, SchemaRequest


class MiningWidgetBot:
    """Bot that interacts with the MiningWidget.

    Attributes
    ----------
    mining_widget : MiningWidget
        Instance of the MiningWidget.

    capsys : pytest.fixture
        Captures standard output. It will enable us to capture print statements done by the
        mining widget.

    monkeypatch : pytest.fixture
        Allows for easy patching. Note that we patch the `display` function of IPython.
        This way we are going to be able to capture all the objects the
        `mining_widget.widgets['out']` holds.
    """

    def __init__(self, mining_widget, capsys, monkeypatch):
        self.mining_widget = mining_widget
        self._display_cached = []
        self._capsys = capsys

        monkeypatch.setattr('bbsearch.widgets.mining_widget.display',
                            lambda x: self._display_cached.append(x))

    @property
    def display_cached(self):
        """Return list of displayed objects and clear history."""
        dc_copy = copy(self._display_cached)
        del self._display_cached[:]
        return dc_copy

    @property
    def stdout_cached(self):
        """Return string of standard output and clear history"""
        return self._capsys.readouterr().out

    def click(self, widget_name):
        """Click a widget.

        Parameters
        ----------
        widget_name : str
            Name of the widget.
        """
        self.mining_widget.widgets[widget_name].click()

    def get_value(self, widget_name):
        """Get a value of a chosen widget.

        Parameters
        ----------
        widget_name : str
            Name of the widget.

        Returns
        -------
        value : Any
            Current value of the widget.
        """
        return self.mining_widget.widgets[widget_name].value

    def set_value(self, widget_name, value):
        """Set a value of a chosen widget.

        Note that this works with multiple different widgets like sliders, dropdowns, ...

        Parameters
        ----------
        widget_name : str
            Name of the widget.

        value : Any
            Value to set the widget to. The type depends on the widget.
        """
        self.mining_widget.widgets[widget_name].value = value


columns = {'name': pd.Series(['John Smith', 'Erica Meyers']),
           'department': pd.Series(['Accounting', 'IT']),
           'birthday': pd.Series(['November', 'March'])}
table_extractions = pd.DataFrame(columns)

TESTS_PATH = Path(__file__).resolve().parent.parent

schema_request = SchemaRequest()
schema_file = TESTS_PATH / 'data' / 'mining' / 'request' / 'request.csv'
df_schema = pd.read_csv(schema_file)
schema_request.schema = df_schema


def request_callback(request):
    dataframe = table_extractions.to_csv(index=False)
    resp_body = {'warnings': ['This is a test warning'],
                 'csv_extractions': dataframe}
    headers = {'request-id': '1234abcdeABCDE'}
    response = (200, headers, json.dumps(resp_body))
    return response


@responses.activate
def test_mining_text(monkeypatch, capsys):

    responses.add_callback(
        responses.POST, 'http://test/text',
        callback=request_callback,
        content_type="application/json"
    )

    mining_widget = MiningWidget(mining_server_url='http://test',
                                 schema_request=schema_request)

    bot = MiningWidgetBot(mining_widget, capsys, monkeypatch)
    bot.set_value('input_text', 'HELLO')
    bot.click('mine_text')

    assert len(responses.calls) == 1

    display_objs = bot.display_cached
    assert len(display_objs) == 3  # 1 schema + 1 warning + 1 table_extractions
    assert isinstance(display_objs[0], pd.DataFrame)

    assert display_objs[0].equals(df_schema)
    assert isinstance(display_objs[1], HTML)
    assert display_objs[2].equals(table_extractions)


@responses.activate
def test_mining_database(monkeypatch, capsys, fake_sqlalchemy_engine):

    responses.add_callback(
        responses.POST, 'http://test/database',
        callback=request_callback,
        content_type="text/csv"
    )

    mining_widget = MiningWidget(mining_server_url='http://test',
                                 schema_request=schema_request)
    empty_dataframe = pd.DataFrame()
    assert empty_dataframe.equals(mining_widget.get_extracted_table())

    bot = MiningWidgetBot(mining_widget, capsys, monkeypatch)
    bot.set_value('input_text', 'HELLO')
    bot.click('mine_articles')

    assert len(responses.calls) == 0
    assert 'No article saver was provided. Nothing to mine.' in bot.stdout_cached

    article_saver = ArticleSaver(fake_sqlalchemy_engine)
    for i in range(2):
        article_saver.add_article(article_id=i)

    mining_widget = MiningWidget(mining_server_url='http://test',
                                 schema_request=schema_request,
                                 article_saver=article_saver)

    bot = MiningWidgetBot(mining_widget, capsys, monkeypatch)
    bot.set_value('input_text', 'HELLO')
    bot.click('mine_articles')

    assert len(responses.calls) == 1
    assert "Collecting saved items..." in bot.stdout_cached
    assert isinstance(mining_widget.get_extracted_table(), pd.DataFrame)

    display_objs = bot.display_cached
    assert len(display_objs) == 3  # 1 schema + 1 warning + 1 table_extractions
    assert isinstance(display_objs[0], pd.DataFrame)
    assert isinstance(display_objs[2], pd.DataFrame)

    assert display_objs[0].equals(df_schema)
    assert isinstance(display_objs[1], HTML)
    assert display_objs[2].equals(table_extractions)