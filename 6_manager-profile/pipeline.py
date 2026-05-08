import os
from agent_pipeline import ManagerEnrichmentPipelineV2

class ManagerEnrichmentPipeline:
    def __init__(self, model_name: str = None):
        self.v2 = ManagerEnrichmentPipelineV2()

    async def run(self, profile_path: str):
        return await self.v2.run(profile_path)
