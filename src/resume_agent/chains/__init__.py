"""Small, typed LangChain tasks used by the resume workflow."""

from resume_agent.chains.bundle import ChainBundle, build_chain_bundle

__all__ = ["ChainBundle", "build_chain_bundle"]
