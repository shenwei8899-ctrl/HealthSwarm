"""合成健康片段的实际 ID 接入既有检索指标；不运行云 Judge。"""

from yuxi.knowledge.eval.metrics import EvaluationMetricsCalculator, RetrievalMetrics


def evaluate_evidence_retrieval(evidence_ids, gold_ids, *, k=5):
    """gold 独立提供；缺 gold 不作质量结论，空命中使用既有零分语义。"""
    if not gold_ids:
        return {"status": "not_evaluated", "metrics": {}}
    metrics = EvaluationMetricsCalculator.calculate_retrieval_metrics(
        [{"chunk_id": identity} for identity in evidence_ids], gold_ids, [k]
    )
    if not evidence_ids:
        metrics = {
            f"recall@{k}": RetrievalMetrics.recall_at_k([], gold_ids, k),
            f"f1@{k}": RetrievalMetrics.f1_score_at_k([], gold_ids, k),
        }
    return {"status": "synthetic_evaluated", "metrics": metrics}
