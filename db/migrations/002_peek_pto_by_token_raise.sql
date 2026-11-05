-- Make peek_pto_by_token raise INVALID_LINK instead of silently returning 0 rows.
-- n8n Postgres node skips downstream nodes when 0 rows are returned, so the
-- respondToWebhook node is never reached. Raising an exception routes to the
-- continueErrorOutput path, which builds the HTML error page.
CREATE OR REPLACE FUNCTION peek_pto_by_token(p_token text)
RETURNS TABLE (code text, employee_name text, start_date date, end_date date,
               days numeric, reason text, status text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
    SELECT p.code, e.full_name, p.start_date, p.end_date, p.days, p.reason, p.status
    FROM pto_requests p
    JOIN employees e ON e.id = p.employee_id
    WHERE p.approval_token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
      AND p.token_expires_at > now();
  IF NOT FOUND THEN
    RAISE EXCEPTION 'INVALID_LINK: This approval link is invalid or has expired.';
  END IF;
END;
$$;
