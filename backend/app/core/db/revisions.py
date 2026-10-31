"""이 릴리스에서 실제 호환 검증한 DB revision을 코드와 함께 고정한다."""

# expand 전에 구 릴리스도 새 revision을 검증·추가한 호환 릴리스를 먼저 배포한다.
# 환경변수로 임의 revision을 허용하면 schema 검사를 우회하므로 지원하지 않는다.
COMPATIBLE_SCHEMA_REVISIONS = frozenset({"20261026_09", "20261031_10"})
