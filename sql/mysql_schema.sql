-- Assetly MySQL 8.0 presentation layer, analytical views, and stored procedures
-- Core tables and indexes are provisioned via SQLAlchemy declarative models.

CREATE OR REPLACE VIEW vw_asset_overview AS
SELECT 
  a.id AS asset_id,
  a.name AS asset_name,
  c.name AS category_name,
  l.name AS location_name,
  a.status,
  a.condition AS asset_condition,
  a.photo_path,
  a.qr_code,
  a.updated_at
FROM assets a 
LEFT JOIN categories c ON c.id = a.category_id 
LEFT JOIN locations l ON l.id = a.location_id;

CREATE OR REPLACE VIEW vw_asset_tco AS
SELECT 
  t.asset_id,
  t.asset_name,
  t.purchase_total,
  t.maintenance_total,
  t.repair_total,
  t.expense_total,
  (t.purchase_total + t.maintenance_total + t.repair_total + t.expense_total) AS total_cost
FROM (
  SELECT 
    a.id AS asset_id,
    a.name AS asset_name,
    COALESCE((SELECT SUM(base_price + shipping_cost) FROM purchases p WHERE p.asset_id = a.id), 0) AS purchase_total,
    COALESCE((SELECT SUM(cost) FROM maintenance_log m WHERE m.asset_id = a.id), 0) AS maintenance_total,
    COALESCE((SELECT SUM(cost) FROM repairs r WHERE r.asset_id = a.id), 0) AS repair_total,
    COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.asset_id = a.id), 0) AS expense_total
  FROM assets a
) t;

CREATE OR REPLACE VIEW vw_active_loans AS
SELECT 
  b.id AS loan_id,
  b.asset_id,
  a.name AS asset_name,
  b.person_id,
  p.name AS person_name,
  b.borrowed_date,
  b.expected_return_date,
  b.payment_type,
  b.amount,
  b.payment_status,
  b.status
FROM borrowings b 
JOIN assets a ON a.id = b.asset_id 
JOIN people p ON p.id = b.person_id 
WHERE b.status = 'ACTIVE';

CREATE OR REPLACE VIEW vw_overdue_loans AS 
SELECT * 
FROM vw_active_loans 
WHERE expected_return_date < CURRENT_DATE;

CREATE OR REPLACE VIEW vw_consumable_stock AS
SELECT 
  c.id AS consumable_id,
  c.name AS item_name,
  cat.name AS category_name,
  COALESCE(SUM(sm.quantity_change), 0) AS current_stock,
  c.unit,
  c.reorder_level,
  CASE WHEN COALESCE(SUM(sm.quantity_change), 0) <= c.reorder_level THEN 1 ELSE 0 END AS needs_reorder
FROM consumables c 
JOIN categories cat ON cat.id = c.category_id
LEFT JOIN consumable_batches cb ON cb.consumable_id = c.id 
LEFT JOIN stock_movements sm ON sm.batch_id = cb.id 
GROUP BY c.id, c.name, cat.name, c.unit, c.reorder_level;

DROP PROCEDURE IF EXISTS sp_return_asset;
DELIMITER //
CREATE PROCEDURE sp_return_asset(IN p_borrowing_id INT)
BEGIN
  START TRANSACTION;
  UPDATE borrowings 
  SET status = 'RETURNED', actual_return_date = CURRENT_DATE 
  WHERE id = p_borrowing_id AND status = 'ACTIVE';
  
  UPDATE assets a 
  JOIN borrowings b ON b.asset_id = a.id 
  SET a.status = 'AVAILABLE' 
  WHERE b.id = p_borrowing_id;
  COMMIT;
END//
DELIMITER ;
