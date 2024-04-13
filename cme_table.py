import duckdb
import pandas as pd
from great_tables import GT, md, html, nanoplot_options
from asyncer import asyncify
from datetime import datetime, timedelta
import os
import asyncio


class CoronalMassEjectionAstronomer(object):
    def __init__(self, lookback_days=60):
        self.lookback_days = lookback_days
        self.start_date = datetime.now() - timedelta(days=self.lookback_days)
        self.end_date = datetime.now()
        self.daily_data: dict[str, pd.DataFrame | None] = {(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'): None
                           for i in range(0, self.lookback_days)}
        self.current_agg: dict[tuple[str, ...], pd.DataFrame]|None = None

    @property
    def is_loaded(self) -> bool:
        return any(v is not None for v in self.daily_data.values())

    def _load_incremental(self):
        # Check to see if we have today's data
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.daily_data:
            self.daily_data[today] = None
            while len(self.daily_data) > self.lookback_days:
                min_date = min(self.daily_data)
                del(self.daily_data[min_date])
        for date in sorted(self.daily_data.keys(), reverse=True):
            if self.daily_data[date] is None:
                self.daily_data[date] = self.load_day(date)
                # Only do one
                break

    def aggregate(self) -> pd.DataFrame:
        with duckdb.connect(':memory:') as con:
            events_df = pd.concat(self.daily_data.values())
            df = con.sql(f"""
                with all_types as (
                    select unnest(['S','C','O','R','ER']) as type, unnest([1,2,3,4,5]) as type_rank
                ),
                bounds as (
                    select 
                        min(epoch(strptime(time21_5, '%Y-%m-%dT%H:%MZ'))) as min_time,
                        max(epoch(strptime(time21_5, '%Y-%m-%dT%H:%MZ'))) as max_time,
                    from events_df
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
                left join events_df using(type)
                cross join bounds
                group by 1,2
                order by type_rank
            """).df()
        return df.copy()

    def load_day(self, day_str: str) -> pd.DataFrame:
        with duckdb.connect(':memory:') as con:
            try:
                con.sql(f"""
                    create or replace table cme_events as (
                        with raw as (
                            select 
                                * 
                            from read_json_auto(
                                'https://api.nasa.gov/DONKI/CME?startDate={day_str}&endDate={day_str}&api_key={os.environ['NASA_API_KEY']}'
                            )
                        ),
                        unnested as (
                                -- explodes the list
                                select *, unnest(cmeAnalyses) as cmeAnalysis from raw
                            ),
                        -- unpacks the struct into columns
                        exploded as (
                            select *, unnest(cmeAnalysis) from unnested
                        )
                        select 
                            activityID,
                            time21_5,
                            type,
                            speed,
                        from exploded);
                    """)
            except duckdb.BinderException as err:
                # This is a hack, but this error will occur when there's no data
                con.sql(f"""
                    create or replace table cme_events
                    (activityID varchar,
                    time21_5 varchar,
                    type varchar,
                    speed float);
                """)

            df = con.sql('select * from cme_events').df()
        return df.copy()

    def _build_table(self) -> GT:
        start_dt = datetime.strptime(min(k for k,v in self.daily_data.items() if v is not None), "%Y-%m-%d")
        end_dt = datetime.strptime(max(k for k,v in self.daily_data.items() if v is not None), "%Y-%m-%d")
        delta = end_dt - start_dt

        key = tuple(sorted(k for k,v in self.daily_data.items() if v is not None))
        if not self.current_agg or key not in self.current_agg:
            self.current_agg = {key: self.aggregate()}
        summary = self.current_agg[key]

        table = GT(summary.drop(['type_rank', '_max_time_bound'], axis=1), rowname_col="type",
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

    async def load_incremental(self) -> None:
        await asyncify(self._load_incremental)()

    async def load_in_background(self, period_seconds=60) -> None:
        while True:
            await self.load_incremental()
            await asyncio.sleep(period_seconds)

    async def progress_html(self) -> str:
        progress_max = len(self.daily_data)
        progress_current = len([k for k,v in self.daily_data.items() if v is not None])

        return f'<progress id="cme-progress" max="{progress_max}" value="{progress_current}">{progress_current}/{progress_max}</progress>'
