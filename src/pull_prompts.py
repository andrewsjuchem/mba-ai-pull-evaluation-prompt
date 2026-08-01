"""
Script para fazer pull de prompts do LangSmith Prompt Hub.

Este script:
1. Conecta ao LangSmith usando credenciais do .env
2. Faz pull dos prompts do Hub
3. Salva localmente em prompts/bug_to_user_story_v1.yml

SIMPLIFICADO: Usa serialização nativa do LangChain para extrair prompts.
"""

import sys
from datetime import datetime
from dotenv import load_dotenv
from langchain import hub
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()

# Prompt de baixa qualidade publicado no Hub (ponto de partida do desafio)
HUB_PROMPT = "leonanluppi/bug_to_user_story_v1"

# Onde o prompt será salvo localmente
OUTPUT_FILE = "prompts/bug_to_user_story_v1.yml"

# Chave raiz usada no YAML (mesmo nome do prompt, sem o owner)
PROMPT_KEY = "bug_to_user_story_v1"


def _template_text(message) -> str:
    """
    Extrai o texto do template de uma mensagem de um ChatPromptTemplate.

    Args:
        message: Mensagem do prompt (template ou mensagem já materializada)

    Returns:
        Texto do template da mensagem (string vazia se não houver)
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
    Descobre o papel (system/user/assistant) de uma mensagem do prompt.

    Args:
        message: Mensagem do prompt

    Returns:
        'system', 'user', 'assistant' ou 'unknown'
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
    Extrai system_prompt e user_prompt de um template do LangChain.

    Suporta ChatPromptTemplate (múltiplas mensagens) e PromptTemplate simples.

    Args:
        prompt_template: Objeto retornado por hub.pull()

    Returns:
        Dicionário com as chaves 'system_prompt' e 'user_prompt'
    """
    messages = getattr(prompt_template, "messages", None)

    if not messages:
        # PromptTemplate simples: todo o conteúdo vira system_prompt
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
    Busca metadados do prompt no LangSmith (descrição, tags, datas).

    Falhas aqui não são fatais: o pull do prompt em si é o que importa.

    Args:
        prompt_identifier: Identificador no formato 'owner/nome'

    Returns:
        Dicionário com metadados encontrados (vazio se indisponível)
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
    Monta a estrutura YAML do prompt a partir do template e dos metadados.

    Args:
        prompt_template: Objeto retornado por hub.pull()
        prompt_identifier: Identificador no formato 'owner/nome'
        metadata: Metadados obtidos do LangSmith

    Returns:
        Dicionário pronto para ser salvo em YAML
    """
    texts = extract_prompt_texts(prompt_template)
    hub_metadata = getattr(prompt_template, "metadata", None) or {}

    return {
        PROMPT_KEY: {
            "description": metadata.get("description")
            or "Prompt para converter relatos de bugs em User Stories",
            "system_prompt": texts["system_prompt"] + "\n",
            "user_prompt": texts["user_prompt"],
            # Metadados
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
    Faz pull do prompt do LangSmith Hub e salva localmente em YAML.

    Returns:
        True se sucesso, False caso contrário
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
    """Função principal"""
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
