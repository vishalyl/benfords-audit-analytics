DROP TABLE IF EXISTS transactions_raw;
CREATE TABLE transactions_raw (
    line_no       INTEGER,
    invoice       TEXT,
    stock_code    TEXT,
    description   TEXT,
    quantity      INTEGER,
    invoice_date  TEXT,          -- ISO-8601
    price         REAL,
    customer_id   TEXT,
    country       TEXT,
    source_sheet  TEXT,
    amount        REAL
);
CREATE INDEX idx_tr_customer ON transactions_raw(customer_id);
CREATE INDEX idx_tr_country  ON transactions_raw(country);
CREATE INDEX idx_tr_date     ON transactions_raw(invoice_date);
CREATE INDEX idx_tr_invoice  ON transactions_raw(invoice);
CREATE INDEX idx_tr_amount   ON transactions_raw(amount);
