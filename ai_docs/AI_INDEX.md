# AI_INDEX

## Repository Summary

- Directories : 66
- Python Files : 286
- Markdown Files : 118
- Config Files : 2

## Entry Points

- `app\cli.py` (cli module)
- `main.py` (well-known entry point)
- `presentation\cli.py` (cli module)
- `presentation\ebay_catalog_cli.py` (entry suffix)
- `tests\test_cli.py` (entry suffix)
- `tests\test_cli_dashboard_integration.py` (cli module)
- `tests\test_ebay_catalog_cli.py` (entry suffix)
- `tests\test_presentation_cli.py` (entry suffix)
- `tests\test_watchlist_monitor_cli.py` (entry suffix)

## Domains

### api

- `app\infrastructure\opportunity_intelligence\discovery_result_adapter.py`
- `app\infrastructure\watchlist\listing_lookup_adapter.py`
- `engine\price_snapshot_adapter.py`
- `tests\contracts\test_marketplace_adapter_contract.py`
- `tests\test_listing_lookup_adapter.py`
- `tests\test_price_snapshot_adapter.py`

### canonical

- `app\models\canonical_product.py`
- `engine\canonical_id_generator.py`
- `tests\test_canonical_id_generator.py`
- `tests\test_canonical_product.py`
- `tests\test_product_draft_identity_policy.py`

### change

- `app\application\change\__init__.py`
- `app\application\change\detect_changes.py`
- `app\application\change\detect_latest_price_change.py`
- `app\application\change\models.py`
- `app\application\change\ports.py`
- `app\domain\change\__init__.py`
- `app\domain\change\detection.py`
- `app\domain\change\event_factory.py`
- `app\domain\change\events.py`
- `app\domain\change\models.py`
- `app\domain\change\publisher.py`
- `app\infrastructure\change\__init__.py`
- `app\infrastructure\change\price_history_snapshot_provider.py`
- `check_price_history.py`
- `engine\price_snapshot_adapter.py`
- `market_data\inventory_snapshot.py`
- `market_data\price_snapshot.py`
- `market_data\seller_snapshot.py`
- `market_data\snapshot.py`
- `market_data\snapshot_mapper.py`
- `storage\opportunity_history.py`
- `storage\price_history.py`
- `tests\test_change_application.py`
- `tests\test_change_detection.py`
- `tests\test_change_events.py`
- `tests\test_change_models.py`
- `tests\test_detect_latest_price_change.py`
- `tests\test_inventory_snapshot.py`
- `tests\test_market_snapshot.py`
- `tests\test_opportunity_history.py`
- `tests\test_orchestrator_price_change_detection.py`
- `tests\test_orchestrator_price_snapshot.py`
- `tests\test_orchestrator_price_snapshot_persistence.py`
- `tests\test_price_change_pipeline_e2e.py`
- `tests\test_price_history.py`
- `tests\test_price_history_snapshot_provider.py`
- `tests\test_price_snapshot.py`
- `tests\test_price_snapshot_adapter.py`
- `tests\test_seller_snapshot.py`
- `tests\test_snapshot.py`
- `tests\test_snapshot_analysis_flow.py`
- `tests\test_snapshot_mapper.py`

### discovery

- `app\application\discovery\__init__.py`
- `app\application\discovery\discover_opportunities.py`
- `app\application\discovery\ports.py`
- `app\application\discovery\session.py`
- `app\application\discovery\statistics.py`
- `app\application\discovery\workflow.py`
- `app\domain\discovery\__init__.py`
- `app\domain\discovery\models.py`
- `app\domain\discovery\pipeline.py`
- `app\domain\discovery\queue.py`
- `app\domain\discovery\ranking.py`
- `app\infrastructure\discovery\__init__.py`
- `app\infrastructure\discovery\orchestrator_gateway.py`
- `app\infrastructure\opportunity_intelligence\discovery_result_adapter.py`
- `tests\test_discovery_application.py`
- `tests\test_discovery_domain.py`
- `tests\test_discovery_workflow_intelligence.py`

### matching

- `engine\product_matching.py`
- `tests\test_product_matching.py`
- `tests\test_product_matching_v2.py`
- `tools\ai\matcher.py`

### opportunity

- `app\application\opportunity_intelligence\__init__.py`
- `app\application\opportunity_intelligence\decision_report.py`
- `app\application\opportunity_intelligence\decision_report_renderer.py`
- `app\application\opportunity_intelligence\final_recommendation.py`
- `app\application\opportunity_intelligence\models.py`
- `app\application\opportunity_intelligence\ports.py`
- `app\application\opportunity_intelligence\service.py`
- `app\application\opportunity_intelligence\trend_interpreter.py`
- `app\domain\opportunity\__init__.py`
- `app\domain\opportunity\decision.py`
- `app\domain\opportunity\evaluation.py`
- `app\domain\opportunity\models.py`
- `app\domain\opportunity\reasons.py`
- `app\engine\opportunity_confidence.py`
- `app\engine\opportunity_decision.py`
- `app\engine\opportunity_risk.py`
- `app\engine\opportunity_score.py`
- `app\infrastructure\opportunity_intelligence\__init__.py`
- `app\infrastructure\opportunity_intelligence\discovery_result_adapter.py`
- `engine\explainable_score.py`
- `engine\opportunity.py`
- `engine\score_formatter.py`
- `storage\opportunity_history.py`
- `tests\test_explainable_score.py`
- `tests\test_explainable_score_market_adjustment.py`
- `tests\test_opportunity.py`
- `tests\test_opportunity_confidence_engine.py`
- `tests\test_opportunity_decision_engine.py`
- `tests\test_opportunity_decision_report.py`
- `tests\test_opportunity_domain.py`
- `tests\test_opportunity_evaluation.py`
- `tests\test_opportunity_final_recommendation.py`
- `tests\test_opportunity_history.py`
- `tests\test_opportunity_intelligence_integration.py`
- `tests\test_opportunity_intelligence_service_enrichment.py`
- `tests\test_opportunity_list_formatter.py`
- `tests\test_opportunity_risk_engine.py`
- `tests\test_opportunity_score_engine.py`
- `tests\test_opportunity_trend_interpreter.py`
- `tests\test_score_formatter.py`

### pricing

- `app\application\change\detect_latest_price_change.py`
- `app\infrastructure\change\price_history_snapshot_provider.py`
- `app\infrastructure\watchlist\price_observation_recorder.py`
- `check_price_history.py`
- `check_price_trend.py`
- `engine\price_intelligence.py`
- `engine\price_snapshot_adapter.py`
- `engine\price_trend.py`
- `market_data\price_snapshot.py`
- `storage\price_history.py`
- `tests\test_detect_latest_price_change.py`
- `tests\test_orchestrator_price_change_detection.py`
- `tests\test_orchestrator_price_snapshot.py`
- `tests\test_orchestrator_price_snapshot_persistence.py`
- `tests\test_price_change_pipeline_e2e.py`
- `tests\test_price_history.py`
- `tests\test_price_history_snapshot_provider.py`
- `tests\test_price_intelligence.py`
- `tests\test_price_observation_recorder.py`
- `tests\test_price_snapshot.py`
- `tests\test_price_snapshot_adapter.py`
- `tests\test_price_trend.py`
- `tests\test_price_trend_domain.py`
- `tests\test_shipping_cost_resolver.py`

### storage

- `app\infrastructure\watchlist\sqlite_repository.py`
- `database\__init__.py`
- `database\models.py`
- `engine\catalog_repository.py`
- `storage\__init__.py`
- `storage\opportunity_history.py`
- `storage\price_history.py`
- `tests\test_catalog_repository.py`
- `tests\test_sqlite_watchlist_repository.py`
