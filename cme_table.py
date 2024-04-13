import duckdb
from great_tables import GT, md, html, nanoplot_options
from asyncer import asyncify
from datetime import datetime, timedelta
import os
import anyio


class CoronalMassEjectionAstronomer(object):
    def __init__(self, lookback_days=60):
        self.lookback_days = lookback_days
        self.con = duckdb.connect(':memory:')
        self.start_date: None | datetime = None
        self.end_date: None | datetime = None

    @property
    def is_loaded(self) -> bool:
        return ('cme_raw',) in self.con.sql('show tables').fetchall()

    def load(self):
        self.start_date = datetime.now() - timedelta(days=self.lookback_days)
        self.end_date = datetime.now()

        self.con.sql(f"""
            create or replace table cme_raw as 
                select 
                    * 
                from read_json_auto(
                    'https://api.nasa.gov/DONKI/CME?startDate={self.start_date.strftime('%Y-%m-%d')}&endDate={self.end_date.strftime('%Y-%m-%d')}&api_key={os.environ['NASA_API_KEY']}'
                );
            create or replace view cme_events as (
                with unnested as (
                    -- explodes the list
                    select *, unnest(cmeAnalyses) as cmeAnalysis from cme_raw
                )
                -- unpacks the struct into columns
                select *, unnest(cmeAnalysis) from unnested
            );
            create or replace view cme_summary as (
                with all_types as (
                    select unnest(['S','C','O','R','ER']) as type, unnest([1,2,3,4,5]) as type_rank
                ),
                bounds as (
                    select 
                        min(epoch(strptime(time21_5, '%Y-%m-%dT%H:%MZ'))) as min_time,
                        max(epoch(strptime(time21_5, '%Y-%m-%dT%H:%MZ'))) as max_time,
                    from cme_events
                )

                select
                    type_rank, 
                    type, 
                    count(activityID) as cme_count, 
                    min(speed) as slowest, 
                    avg(speed) as average,
                    max(speed) as fastest, 
                    {{'x': coalesce(
                            string_agg(
                                epoch(strptime(time21_5, '%Y-%m-%dT%H:%MZ'))-min_time, ' ' order by time21_5), ''),
                    'y': coalesce(
                            string_agg(speed, ' ' order by time21_5),'')}} as speeds,
                    any_value(max_time) - any_value(min_time) as _max_time_bound
                from all_types
                left join cme_events using(type)
                cross join bounds
                group by 1,2
                order by type_rank
            );
            """)

    def _build_table(self) -> GT:
        summary = self.con.sql('select * from cme_summary').df()
        table = GT(summary.drop(['type_rank', '_max_time_bound'], axis=1), rowname_col="type",
                   ).tab_header(
            title="Coronal Mass Ejections",
            subtitle="CMEs from the last month"
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
            options=nanoplot_options(
                show_data_area=False,
            )
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
        )

        return table

    async def table_html(self) -> str:
        table = await asyncify(self._build_table)()
        return table.as_raw_html()