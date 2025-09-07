# ReAct Beyond Language Models
When people talk about agentic AI, the conversation often involves large language models (LLMs).  ReAct — short for Reason + Act — is a popular pattern for building agents.  

Most examples you see present ReAct in the context of LLM-backed reasoning, i.e., where the “Thought → Action → Observation” loop is orchestrated by a language model. 

However, an LLM is actually not required. In domains like finance where predictable execution matters, a deterministic reasoning step is sometimes more desirable.