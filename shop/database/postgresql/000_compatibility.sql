-- Compatibility helpers for legacy FastAdmin SQL expressions.
CREATE OR REPLACE FUNCTION find_in_set(needle text, haystack text)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(array_position(string_to_array(COALESCE(haystack, ''), ','), needle), 0);
$$;
