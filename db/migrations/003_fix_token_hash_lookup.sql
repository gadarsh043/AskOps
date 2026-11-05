-- Fix token hash comparison: the token stored in email links is the hex encoding
-- of 32 raw bytes (encode(raw, 'hex')). To verify, we must decode the hex back
-- to bytes before hashing: decode(p_token, 'hex'). Using convert_to(p_token, 'UTF8')
-- hashes the hex string itself (64 ASCII chars), which never matches.
CREATE OR REPLACE FUNCTION peek_pto_by_token(p_token text)
RETURNS TABLE (code text, employee_name text, start_date date, end_date date,
               days numeric, reason text, status text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
    SELECT p.code, e.full_name, p.start_date, p.end_date, p.days, p.reason, p.status
    FROM pto_requests p
    JOIN employees e ON e.id = p.employee_id
    WHERE p.approval_token_hash = encode(sha256(decode(p_token, 'hex')), 'hex')
      AND p.token_expires_at > now();
  IF NOT FOUND THEN
    RAISE EXCEPTION 'INVALID_LINK: This approval link is invalid or has expired.';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION decide_pto_by_token(p_token text, p_decision text, p_note text DEFAULT NULL)
RETURNS pto_requests LANGUAGE plpgsql AS $$
DECLARE
  v_id uuid;
BEGIN
  SELECT id INTO v_id
  FROM pto_requests
  WHERE approval_token_hash = encode(sha256(decode(p_token, 'hex')), 'hex')
    AND token_expires_at > now();

  IF v_id IS NULL THEN
    RAISE EXCEPTION 'INVALID_LINK: link is invalid, expired or already used';
  END IF;

  RETURN decide_pto(v_id, p_decision, 'email', p_note);
END $$;
