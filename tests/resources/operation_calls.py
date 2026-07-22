"""Typed invocation dispatcher covering every async public API operation."""

from __future__ import annotations

from parampilot import AsyncParamPilot
from parampilot.models import (
    CampaignAccessGrantRequest,
    CampaignCreateRequest,
    CampaignSettingsRequest,
    CampaignTransferLinkRequest,
    ConfiguredCampaignCreateRequest,
    Domain,
    ExperimentBatchUpsertItem,
    ExperimentBatchUpsertRequest,
    ExperimentPatchRequest,
    ExtraData,
    RandomStrategy,
)
from tests.support import CAMPAIGN_ID, EXPERIMENT_ID, JOB_ID


async def invoke_operation(
    client: AsyncParamPilot,
    operation_id: str,
    domain: Domain,
    strategy: RandomStrategy,
) -> object:
    """Invoke one operation with the smallest valid typed request values.

    Args:
        client: Async SDK client backed by an external fake transport.
        operation_id: Stable operation ID to invoke.
        domain: Minimal valid optimization domain.
        strategy: Minimal valid random strategy for that domain.

    Returns:
        Operation result when the external transport does not reject it.

    Raises:
        AssertionError: If the dispatcher lacks the reviewed operation.

    """
    if operation_id == "getAvailability":
        return await client.get_availability()
    if operation_id == "archiveCampaign":
        return await client.campaigns.archive(CAMPAIGN_ID, if_match='"v1"')
    if operation_id == "createCampaign":
        return await client.campaigns.create(CampaignCreateRequest(name="test"))
    if operation_id == "createConfiguredCampaign":
        return await client.campaigns.create_configured(
            ConfiguredCampaignCreateRequest(
                name="test",
                domain=domain,
                strategy=strategy,
                additional_fields=ExtraData(fields=[]),
                effects=[],
            )
        )
    if operation_id == "getCampaign":
        return await client.campaigns.get(CAMPAIGN_ID)
    if operation_id == "getCampaignStatus":
        return await client.campaigns.get_status(CAMPAIGN_ID)
    if operation_id == "listCampaigns":
        return await client.campaigns.list()
    if operation_id == "replaceCampaignAdditionalFields":
        return await client.campaigns.replace_additional_fields(
            CAMPAIGN_ID,
            ExtraData(fields=[]),
            if_match='"v1"',
        )
    if operation_id == "replaceCampaignDomain":
        return await client.campaigns.replace_domain(
            CAMPAIGN_ID,
            domain,
            if_match='"v1"',
        )
    if operation_id == "replaceCampaignEffects":
        return await client.campaigns.replace_effects(
            CAMPAIGN_ID,
            [],
            if_match='"v1"',
        )
    if operation_id == "replaceCampaignStrategy":
        return await client.campaigns.replace_strategy(
            CAMPAIGN_ID,
            strategy,
            if_match='"v1"',
        )
    if operation_id == "startCampaign":
        return await client.campaigns.start(CAMPAIGN_ID, if_match='"v1"')
    if operation_id == "unlockCampaign":
        return await client.campaigns.unlock(CAMPAIGN_ID, if_match='"v1"')
    if operation_id == "updateCampaignSettings":
        return await client.campaigns.update_settings(
            CAMPAIGN_ID,
            CampaignSettingsRequest(name="updated"),
            if_match='"v1"',
        )
    if operation_id == "listCampaignAccessGrants":
        return await client.campaign_access.list(CAMPAIGN_ID)
    if operation_id == "upsertCampaignAccessGrant":
        return await client.campaign_access.upsert(
            CAMPAIGN_ID,
            CampaignAccessGrantRequest(username="collaborator", access_level="read"),
            if_match='"v1"',
        )
    if operation_id == "deleteCampaignAccessGrant":
        return await client.campaign_access.delete(
            CAMPAIGN_ID,
            EXPERIMENT_ID,
            if_match='"v1"',
        )
    if operation_id == "createCampaignTransferLink":
        return await client.campaign_transfer_links.create(
            CAMPAIGN_ID,
            CampaignTransferLinkRequest(
                source_campaign_id=EXPERIMENT_ID,
                input_mappings={"source": "target"},
            ),
            if_match='"v1"',
        )
    if operation_id == "deleteCampaignTransferLink":
        return await client.campaign_transfer_links.delete(
            CAMPAIGN_ID,
            EXPERIMENT_ID,
            if_match='"v1"',
        )
    if operation_id == "listExperiments":
        return await client.experiments.list(CAMPAIGN_ID)
    if operation_id == "batchUpsertExperiments":
        return await client.experiments.batch_upsert(
            CAMPAIGN_ID,
            ExperimentBatchUpsertRequest(
                items=[ExperimentBatchUpsertItem(labcode="ex-1")]
            ),
        )
    if operation_id == "importExperimentsFile":
        return await client.experiments.import_file(
            CAMPAIGN_ID,
            b"labcode\nex-1\n",
            filename="experiments.csv",
            content_type="text/csv",
        )
    if operation_id == "getExperiment":
        return await client.experiments.get(CAMPAIGN_ID, EXPERIMENT_ID)
    if operation_id == "patchExperiment":
        return await client.experiments.patch(
            CAMPAIGN_ID,
            EXPERIMENT_ID,
            ExperimentPatchRequest(outputs={"yield": 90.0}),
            if_match='"v1"',
        )
    if operation_id == "deleteExperiment":
        return await client.experiments.delete(
            CAMPAIGN_ID,
            EXPERIMENT_ID,
            if_match='"v1"',
        )
    if operation_id == "exportExperiments":
        return await client.experiments.export(CAMPAIGN_ID)
    if operation_id == "queryEffectiveExperiments":
        return await client.experiments.query_effective(CAMPAIGN_ID)
    if operation_id == "exportEffectiveExperiments":
        return await client.experiments.export_effective(CAMPAIGN_ID)
    if operation_id == "createTrainingJob":
        return await client.model_jobs.train_model(CAMPAIGN_ID)
    if operation_id == "createAskJob":
        return await client.model_jobs.create_ask_job(CAMPAIGN_ID, n=1)
    if operation_id == "createPredictionJob":
        return await client.model_jobs.create_prediction_job(
            CAMPAIGN_ID,
            rows=[{"temperature": 80.0}],
        )
    if operation_id == "listModelJobs":
        return await client.model_jobs.list(CAMPAIGN_ID)
    if operation_id == "getModelJob":
        return await client.model_jobs.get(CAMPAIGN_ID, JOB_ID)
    if operation_id == "getModelJobObservation":
        return await client.model_jobs.get_observation(CAMPAIGN_ID, JOB_ID)
    if operation_id == "listModelJobObservations":
        return await client.model_jobs.list_observations(CAMPAIGN_ID)
    if operation_id == "cancelModelJob":
        return await client.model_jobs.cancel(CAMPAIGN_ID, JOB_ID)
    if operation_id == "getModelJobResult":
        return await client.model_jobs.get_result(CAMPAIGN_ID, JOB_ID)
    if operation_id == "downloadGridPredictions":
        return await client.model_artifacts.download_grid_predictions(CAMPAIGN_ID)
    if operation_id == "getShapResults":
        return await client.model_artifacts.get_shap_results(CAMPAIGN_ID)
    raise AssertionError(f"No async invocation fixture for {operation_id}")
