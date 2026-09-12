-- =============================================================
-- Q1. Transaction value and volume by country and month
-- Audit purpose: establishes the population and identifies
-- geographic/temporal concentrations that warrant segment testing.
-- =============================================================
SELECT
    country,
    strftime('%Y-%m', invoice_date)              AS year_month,
    COUNT(*)                                      AS txn_count,
    ROUND(SUM(amount), 2)                         AS total_value,
    ROUND(AVG(amount), 2)                         AS avg_value,
    ROUND(MIN(amount), 2)                         AS min_value,
    ROUND(MAX(amount), 2)                         AS max_value
FROM transactions_raw
WHERE amount > 0
GROUP BY country, year_month
ORDER BY total_value DESC;

-- =============================================================
-- Q2. Top 20 customers by total transaction value
-- Audit purpose: revenue concentration. A small number of
-- customers driving most revenue raises both a going-concern
-- consideration and a targeted-testing opportunity.
-- =============================================================
SELECT
    customer_id,
    country,
    COUNT(DISTINCT invoice)                       AS invoice_count,
    COUNT(*)                                      AS line_count,
    ROUND(SUM(amount), 2)                         AS total_value,
    ROUND(AVG(amount), 2)                         AS avg_line_value,
    MIN(invoice_date)                             AS first_txn,
    MAX(invoice_date)                             AS last_txn
FROM transactions_raw
WHERE customer_id IS NOT NULL
  AND customer_id <> 'UNASSIGNED'
  AND amount > 0
GROUP BY customer_id, country
ORDER BY total_value DESC
LIMIT 20;

-- =============================================================
-- Q3. Duplicate-candidate detection
-- Audit purpose: duplicate billing / duplicate revenue recognition.
-- Same customer, same value, same calendar day, more than one
-- distinct invoice = candidate for duplicate-payment testing.
-- =============================================================
SELECT
    customer_id,
    DATE(invoice_date)                            AS txn_date,
    ROUND(amount, 2)                              AS amount_rounded,
    COUNT(*)                                      AS occurrences,
    COUNT(DISTINCT invoice)                       AS distinct_invoices,
    GROUP_CONCAT(DISTINCT invoice)                AS invoice_list,
    ROUND(SUM(amount), 2)                         AS total_exposure
FROM transactions_raw
WHERE amount > 0
  AND customer_id IS NOT NULL
GROUP BY customer_id, txn_date, amount_rounded
HAVING COUNT(*) > 1
   AND COUNT(DISTINCT invoice) > 1
ORDER BY total_exposure DESC
LIMIT 200;

-- =============================================================
-- Q4. Monthly transaction volume trend + period-end concentration
-- Audit purpose: cut-off testing. An abnormal share of the month's
-- volume booked in the final two days suggests period-end pressure.
-- =============================================================
WITH monthly AS (
    SELECT
        strftime('%Y-%m', invoice_date)           AS year_month,
        COUNT(*)                                   AS txn_count,
        SUM(amount)                                AS total_value,
        SUM(CASE
              WHEN CAST(strftime('%d', invoice_date) AS INTEGER) >=
                   CAST(strftime('%d', DATE(invoice_date,'start of month','+1 month','-2 day')) AS INTEGER)
              THEN 1 ELSE 0 END)                   AS last2day_count
    FROM transactions_raw
    WHERE amount > 0
    GROUP BY year_month
)
SELECT
    year_month,
    txn_count,
    ROUND(total_value, 2)                          AS total_value,
    last2day_count,
    ROUND(100.0 * last2day_count / txn_count, 2)   AS pct_in_last_2_days
FROM monthly
ORDER BY year_month;

-- =============================================================
-- Q5 (bonus). Leading-digit distribution straight in SQL
-- Audit purpose: demonstrates Benford extraction without Python,
-- useful when the only access to client data is a read-only DB.
-- =============================================================
WITH positive AS (
    SELECT CAST(SUBSTR(
        REPLACE(printf('%.2f', amount), '.', ''), 1, 1) AS INTEGER) AS lead_digit
    FROM transactions_raw
    WHERE amount >= 1.0
)
SELECT
    lead_digit,
    COUNT(*)                                       AS observed_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS observed_pct
FROM positive
WHERE lead_digit BETWEEN 1 AND 9
GROUP BY lead_digit
ORDER BY lead_digit;

-- =============================================================
-- Q6 (bonus). Round-amount concentration by customer
-- Audit purpose: manual journal entries and estimates cluster on
-- round numbers; system-generated sales rarely do.
-- =============================================================
SELECT
    customer_id,
    COUNT(*)                                       AS txn_count,
    SUM(CASE WHEN amount > 0 AND CAST(amount AS INTEGER) = amount
             AND CAST(amount AS INTEGER) % 100 = 0
        THEN 1 ELSE 0 END)                         AS round_100_count,
    ROUND(100.0 * SUM(CASE WHEN amount > 0 AND CAST(amount AS INTEGER) = amount
             AND CAST(amount AS INTEGER) % 100 = 0
        THEN 1 ELSE 0 END) / COUNT(*), 2)          AS pct_round_100
FROM transactions_raw
WHERE amount > 0 AND customer_id IS NOT NULL
GROUP BY customer_id
HAVING COUNT(*) >= 50
ORDER BY pct_round_100 DESC
LIMIT 25;
