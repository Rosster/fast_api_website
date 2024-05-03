from great_tables import GT, md, html, nanoplot_options
import great_tables
import pandas as pd
from datetime import datetime

import js

##################
# HORRIFIC PATCH #
##################
def _map_is_na(x: list) -> list[bool]:
    # TODO: all([]) returns True. Let's double check all places
    # in the code that call all() with this function. Do they work as intended?
    return [pd.isnull(val) for val in x]

def _is_na(x) -> bool:
    return pd.isnull(x)

great_tables._utils_nanoplots._map_is_na =_map_is_na
great_tables._utils_nanoplots._is_na =_is_na

######################
# END HORRIFIC PATCH #
######################

summary = pd.DataFrame.from_records(js.window.cme_summary_data.to_py())
cme_event_data: dict[str:list[dict]] = js.window.cme_data.to_py()
start_dt = datetime.strptime(min(cme_event_data), '%Y-%m-%d')
end_dt = datetime.strptime(max(cme_event_data), '%Y-%m-%d')
delta = end_dt - start_dt

table = (GT(summary.drop(['type_rank', '_max_time_bound'], axis=1), rowname_col="type",
           ).tab_header(
    title="Coronal Mass Ejections",
    subtitle=f"CMEs from {start_dt.strftime('%B %d, %Y')} to {end_dt.strftime('%B %d, %Y')} ({delta.days + 1:.0f} days)"
).tab_options(
    table_background_color="#fffff8",
).tab_stubhead(
    label="Type"
).fmt_integer(columns=[
    'cme_count'
    'slowest',
    'average',
    'fastest'
]).fmt_nanoplot(
    columns="speeds",
    expand_x=[0, summary._max_time_bound.max()],
    # options=nanoplot_options(
    #     show_data_area=False,
    # )
).cols_label(
    cme_count=html("CME<br>Count"),
    slowest=html("Slowest Speed,<br>km/s"),
    average=html("Average Speed,<br>km/s"),
    fastest=html("Fastest Speed,<br>km/s"),
    speeds=html("Speed for each event")
).tab_source_note(
    source_note=md(
        "Courtesty of the fine folks at the The [Space Weather Database Of Notifications, Knowledge, Information](https://ccmc.gsfc.nasa.gov/tools/DONKI/) (DONKI). Their acronym, not mine. ")
).tab_source_note(
    source_note=md(
        "CMEs are classified as S (slow), C (common), O (occasional), R (rare), ER (extemely rare) [depending on speed](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/swe.20058).")
))

div = js.document.getElementById("TEST")
div.innerHTML = table.as_raw_html()
