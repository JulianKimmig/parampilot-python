"""Bounded byte-backed asynchronous experiment file imports."""

from __future__ import annotations

from uuid import UUID

from parampilot.import_validation import validated_import_file
from parampilot.models import ExperimentBatchResponse
from parampilot.resources.experiment_exports import ExperimentExportMethods
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import public_id


class ExperimentImportMethods(ExperimentExportMethods):
    """Validated multipart import mixed into the experiment resource."""

    async def import_file(
        self,
        campaign_id: UUID | str,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        idempotency_key: str | None = None,
    ) -> ExperimentBatchResponse:
        """Atomically import bounded CSV or XLSX bytes.

        Args:
            campaign_id: Public campaign UUID.
            data: Complete file bytes, at most 10 MiB.
            filename: Basename including ``.csv`` or ``.xlsx``.
            content_type: Declared supported media type.
            idempotency_key: Optional logical mutation key.

        Returns:
            Ordered one-to-one atomic import results.

        Raises:
            ConfigurationError: If local file metadata or size is unsafe.

        """
        file_value = validated_import_file(
            data,
            filename=filename,
            content_type=content_type,
        )
        return await self._model(
            "importExperimentsFile",
            ExperimentBatchResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            headers=mutation_headers(idempotency=idempotency_key),
            files={"file": file_value},
        )
