from sqlalchemy import text

async def test_ledger_is_balanced(db):
    res = await db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT journal_id
            FROM paylink.ledger_entries
            GROUP BY journal_id
            HAVING
              SUM(CASE WHEN direction='DEBIT' THEN amount ELSE 0 END)
              <>
              SUM(CASE WHEN direction='CREDIT' THEN amount ELSE 0 END)
        ) t
    """))
    assert res.scalar_one() == 0
