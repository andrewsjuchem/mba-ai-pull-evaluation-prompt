"""
Script that pulls prompts from the LangSmith Prompt Hub.

This script:
1. Connects to LangSmith using the credentials from .env
2. Pulls the prompts from the Hub
3. Saves them locally to prompts/bug_to_user_story_v1.yml

SIMPLIFIED: relies on LangChain's native serialization to extract the prompts.
"""

import sys
import yaml
from datetime import datetime
from dotenv import load_dotenv
from langchain import hub
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()


def _represent_multiline_str(dumper, data):
    """Dump multiline strings as literal blocks (|) so they stay readable."""
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


# save_yaml() uses PyYAML's default Dumper; registering here avoids touching utils.py
yaml.add_representer(str, _represent_multiline_str)

# Low-quality prompt published on the Hub (the challenge's starting point)
HUB_PROMPT = "leonanluppi/bug_to_user_story_v1"

# Where the prompt is saved locally
OUTPUT_FILE = "prompts/bug_to_user_story_v1.yml"

# Root key used in the YAML file (the prompt name, without the owner)
PROMPT_KEY = "bug_to_user_story_v1"


def _template_text(message) -> str:
    """
    Extract the template text of a single ChatPromptTemplate message.

    Args:
        message: Prompt message (a template or an already-materialized message)

    Returns:
        The message's template text (empty string when there is none)
    """
    inner = getattr(message, "prompt", None)

    if isinstance(inner, list):
        return "\n\n".join(getattr(p, "template", "") for p in inner).strip()

    if inner is not None:
        return str(getattr(inner, "template", "")).strip()

    content = getattr(message, "content", "")
    return content.strip() if isinstance(content, str) else ""


def _role_of(message) -> str:
    """
    Determine the role (system/user/assistant) of a prompt message.

    Args:
        message: Prompt message

    Returns:
        'system', 'user', 'assistant' or 'unknown'
    """
    name = type(message).__name__.lower()

    if "system" in name:
        return "system"
    if "human" in name or "user" in name:
        return "user"
    if "ai" in name or "assistant" in name:
        return "assistant"

    role = str(getattr(message, "role", "")).lower()
    if role in ("system", "user", "assistant"):
        return role

    return "unknown"


def extract_prompt_texts(prompt_template) -> dict:
    """
    Extract system_prompt and user_prompt from a LangChain template.

    Supports ChatPromptTemplate (multiple messages) and plain PromptTemplate.

    Args:
        prompt_template: Object returned by hub.pull()

    Returns:
        Dictionary with the keys 'system_prompt' and 'user_prompt'
    """
    messages = getattr(prompt_template, "messages", None)

    if not messages:
        # Plain PromptTemplate: the whole content becomes the system_prompt
        return {
            "system_prompt": str(getattr(prompt_template, "template", "")).strip(),
            "user_prompt": "",
        }

    parts = {"system": [], "user": [], "assistant": []}

    for message in messages:
        role = _role_of(message)
        text = _template_text(message)

        if not text or role not in parts:
            continue

        parts[role].append(text)

    return {
        "system_prompt": "\n\n".join(parts["system"]),
        "user_prompt": "\n\n".join(parts["user"]),
    }


def fetch_hub_metadata(prompt_identifier: str) -> dict:
    """
    Fetch the prompt's metadata from LangSmith (description, tags, dates).

    Failures here are not fatal: pulling the prompt itself is what matters.

    Args:
        prompt_identifier: Identifier in the 'owner/name' format

    Returns:
        Dictionary with the metadata found (empty when unavailable)
    """
    try:
        from langsmith import Client

        info = Client().get_prompt(prompt_identifier)

        if info is None:
            return {}

        created_at = getattr(info, "created_at", None)

        return {
            "description": getattr(info, "description", "") or "",
            "tags": list(getattr(info, "tags", None) or []),
            "created_at": created_at.date().isoformat() if created_at else "",
            "is_public": getattr(info, "is_public", None),
        }

    except Exception as e:
        print(f"   ⚠️  Não foi possível ler os metadados do Hub: {e}")
        return {}


def build_prompt_yaml(prompt_template, prompt_identifier: str, metadata: dict) -> dict:
    """
    Build the prompt's YAML structure from the template and its metadata.

    Args:
        prompt_template: Object returned by hub.pull()
        prompt_identifier: Identifier in the 'owner/name' format
        metadata: Metadata retrieved from LangSmith

    Returns:
        Dictionary ready to be saved as YAML
    """
    texts = extract_prompt_texts(prompt_template)
    hub_metadata = getattr(prompt_template, "metadata", None) or {}

    return {
        PROMPT_KEY: {
            "description": metadata.get("description")
            or "Prompt para converter relatos de bugs em User Stories",
            "system_prompt": texts["system_prompt"] + "\n",
            "user_prompt": texts["user_prompt"],
            # Metadata
            "version": "v1",
            "created_at": metadata.get("created_at") or "",
            "tags": metadata.get("tags")
            or ["bug-analysis", "user-story", "product-management"],
            "input_variables": list(
                getattr(prompt_template, "input_variables", None) or []
            ),
            "source": {
                "hub_prompt": prompt_identifier,
                "commit_hash": hub_metadata.get("lc_hub_commit_hash", ""),
                "pulled_at": datetime.now().isoformat(timespec="seconds"),
            },
        }
    }


def pull_prompts_from_langsmith() -> bool:
    """
    Pull the prompt from the LangSmith Hub and save it locally as YAML.

    Returns:
        True on success, False otherwise
    """
    print(f"Puxando prompt do LangSmith Hub: {HUB_PROMPT}")

    try:
        prompt_template = hub.pull(HUB_PROMPT)
    except Exception as e:
        print(f"\n❌ Erro ao fazer pull de '{HUB_PROMPT}': {e}\n")
        print("Verifique:")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
        print("- O prompt existe e está público no LangSmith Hub")
        print("- Sua conexão com a internet está funcionando")
        return False

    print("   ✓ Prompt carregado com sucesso")

    metadata = fetch_hub_metadata(HUB_PROMPT)
    prompt_yaml = build_prompt_yaml(prompt_template, HUB_PROMPT, metadata)

    if not prompt_yaml[PROMPT_KEY]["system_prompt"].strip():
        print("\n❌ O prompt puxado não contém nenhum texto de system prompt.")
        return False

    if not save_yaml(prompt_yaml, OUTPUT_FILE):
        return False

    print(f"   ✓ Prompt salvo em: {OUTPUT_FILE}")

    data = prompt_yaml[PROMPT_KEY]
    print(f"\nResumo:")
    print(f"   - Descrição: {data['description']}")
    print(f"   - Variáveis de entrada: {', '.join(data['input_variables']) or 'nenhuma'}")
    print(f"   - Tamanho do system_prompt: {len(data['system_prompt'])} caracteres")
    print(f"   - Tamanho do user_prompt: {len(data['user_prompt'])} caracteres")
    print(f"   - Commit: {data['source']['commit_hash'] or 'não informado'}")

    return True


def main():
    """Main entry point"""
    print_section_header("PULL DE PROMPTS DO LANGSMITH HUB")

    if not check_env_vars(["LANGSMITH_API_KEY"]):
        return 1

    if not pull_prompts_from_langsmith():
        return 1

    print("\n✅ Pull concluído com sucesso!")
    print("\nPróximos passos:")
    print(f"1. Analise o prompt em {OUTPUT_FILE}")
    print("2. Crie a versão otimizada em prompts/bug_to_user_story_v2.yml")
    print("3. Faça push: python src/push_prompts.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
