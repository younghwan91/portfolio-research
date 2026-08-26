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

    def test_opening_a_current_db_adds_nothing(self, tmp_path) -> None:
        """이미 최신이면 아무것도 하지 않는다 — 열 때마다 ALTER 를 치지 않는다."""
        from opt_portfolio.factor.data.store import META_FIELDS, PITStore

        db = tmp_path / "new.duckdb"
        PITStore(db).close()
        store = PITStore(db)
        assert store._add_missing_columns("tickers", {f: "VARCHAR" for f in META_FIELDS}) == []
        store.close()
