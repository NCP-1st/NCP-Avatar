import pytest

from backend.services.knowledge.base import OntologyFact
from backend.services.knowledge.memory import InMemoryPersonalOntology


@pytest.mark.anyio
async def test_personal_ontology_starts_empty_without_sample_facts() -> None:
    ontology = InMemoryPersonalOntology()

    assert await ontology.related(user_id="user-1", entities=["친구"]) == []


@pytest.mark.anyio
async def test_personal_ontology_uses_explicitly_injected_facts() -> None:
    fact = OntologyFact(
        subject="친구",
        relation="함께 식사함",
        object="사용자",
        observed=True,
        evidence_diary_ids=["diary-1"],
    )
    ontology = InMemoryPersonalOntology([fact])

    assert await ontology.related(user_id="user-1", entities=["친구"]) == [fact]
