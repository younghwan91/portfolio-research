class TestSchemaGrowth:
    """스키마가 자란 뒤 옛 DB 를 열었을 때 조용히 어긋나지 않는다 (CLAUDE.md §1)."""

    def test_missing_column_is_added_and_announced(self, tmp_path, caplog) -> None:
        """`CREATE TABLE IF NOT EXISTS` 는 기존 표에 컬럼을 안 만든다 — 그래서 붙인다.

        붙이지 않으면 업서트가 깨지거나, 더 나쁘게 그 필드가 조용히 빈 채로 남는다.
        """
        import logging

        import duckdb

        from opt_portfolio.factor.data.store import META_FIELDS, PITStore

        db = tmp_path / "old.duckdb"
        # 옛 스키마 — permaticker 가 없던 시절
        old = [f for f in META_FIELDS if f != "permaticker"]
        con = duckdb.connect(str(db))
        cols = ", ".join(f'"{f}" VARCHAR' for f in old)
        con.execute(f"CREATE TABLE tickers (ticker VARCHAR NOT NULL, {cols})")
        con.execute("INSERT INTO tickers (ticker) VALUES ('FOXA')")
        con.close()

        with caplog.at_level(logging.WARNING):
            store = PITStore(db)
        have = {
            str(r[0])
            for r in store.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'tickers'"
            ).fetchall()
        }
        assert "permaticker" in have, "없던 컬럼이 붙어야 한다"
        assert set(META_FIELDS) <= have

        # 기존 행은 남고, 새 컬럼은 비어 있다 — 값을 지어내지 않는다
        row = store.conn.execute("SELECT ticker, permaticker FROM tickers").fetchall()
        assert row == [("FOXA", None)]

        # **붙였으면 말한다**
        assert any("permaticker" in r.getMessage() for r in caplog.records), caplog.text
        store.close()

    def test_upsert_does_not_drop_rows_missing_a_new_field(self, tmp_path) -> None:
        """새 필드가 없는 행도 **떨어지지 않는다** — 행수가 줄면 빌드 게이트가 막힌다.

        quant-airflow 의 `sharadar_build` 는 tickers 행수가 5% 넘게 줄면 그날 공개를
        막는다. `_upsert` 의 `required` 는 키(`ticker`)뿐이라 `permaticker` 결측은
        행 제외 사유가 아니다 — 그 사실을 여기서 붙잡아 둔다.
        """
        import pandas as pd

        from opt_portfolio.factor.data.store import PITStore

        store = PITStore(tmp_path / "s.duckdb")
        # permaticker 열이 아예 없는 프레임 (옛 어댑터가 주던 모양)
        df = pd.DataFrame({"ticker": ["FOXA", "FOX", "CRD.B"], "sector": ["a", "b", "c"]})
        assert store.upsert_tickers(df) == 3, "새 필드가 없어도 3행 전부 들어간다"

        rows = store.conn.execute("SELECT ticker, permaticker FROM tickers ORDER BY 1").fetchall()
        assert [r[0] for r in rows] == ["CRD.B", "FOX", "FOXA"]
        assert all(r[1] is None for r in rows), "없는 값을 지어내지 않는다"
        store.close()

    def test_the_share_class_key_is_relatedtickers_not_permaticker(self) -> None:
        """**`permaticker` 는 클래스를 묶지 못한다** — 2026-08-27 원본 확인으로 뒤집힌 전제.

        Sharadar tickers.csv 실측:
            FOX=111122  vs FOXA=111125
            CRD.B=119318 vs CRD.A=199806
            HVT.A=119307 vs HVT=199171
        전부 다르다. 묶는 것은 `relatedtickers`(형제 티커 목록)와 `secfilings` 안의 CIK 다
        (CRD.A·CRD.B 둘 다 CIK=0000025475).

        이 테스트는 스키마가 **실제로 묶이는 필드**를 싣고 있는지 붙잡아 둔다.
        """
        from opt_portfolio.factor.data.schema import FIELDS

        assert FIELDS["relatedtickers"].vendor["sharadar"] == "relatedtickers"
        assert FIELDS["secfilings"].vendor["sharadar"] == "secfilings"
        # permaticker 도 싣지만 용도가 다르다 — 개명 추적
        assert "개명" in FIELDS["permaticker"].desc

    def test_reingest_does_not_backfill_an_added_column(self, tmp_path) -> None:
        """**재적재로는 안 채워진다** — `merge_fields=False` 라 기존 행을 안 건드린다.

        이걸 모르면 "다시 적재하면 채워진다" 고 잘못 안내하게 된다. 채우려면 스토어를
        새로 짓거나 그 행을 지워야 한다.
        """
        import pandas as pd

        from opt_portfolio.factor.data.store import PITStore

        store = PITStore(tmp_path / "s.duckdb")
        store.upsert_tickers(pd.DataFrame({"ticker": ["FOXA"], "sector": ["a"]}))
        # 이제 값이 있는 채로 다시 넣어 본다
        store.upsert_tickers(pd.DataFrame({"ticker": ["FOXA"], "permaticker": ["199059"]}))
        got = store.conn.execute("SELECT permaticker FROM tickers").fetchone()
        assert got == (None,), "기존 행은 갱신되지 않는다 — 안내 문구가 이 사실을 말해야 한다"
        store.close()

    def test_opening_a_current_db_adds_nothing(self, tmp_path) -> None:
        """이미 최신이면 아무것도 하지 않는다 — 열 때마다 ALTER 를 치지 않는다."""
        from opt_portfolio.factor.data.store import META_FIELDS, PITStore

        db = tmp_path / "new.duckdb"
        PITStore(db).close()
        store = PITStore(db)
        assert store._add_missing_columns("tickers", {f: "VARCHAR" for f in META_FIELDS}) == []
        store.close()
