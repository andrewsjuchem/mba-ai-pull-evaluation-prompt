"""
Script that pushes the optimized prompt to the LangSmith Prompt Hub.

This script:
1. Reads the optimized prompt from prompts/bug_to_user_story_v2.yml
2. Validates the prompt
3. Pushes it PUBLICLY to the LangSmith Hub
4. Adds metadata (tags, description, techniques applied)

SIMPLIFIED: relies on LangChain's native serialization to publish the prompt.
"""

import os
import sys
from dotenv import load_dotenv
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate
from utils import load_yaml, check_env_vars, print_section_header, validate_prompt_structure

load_dotenv()

# Where the optimized prompt is read from
PROMPT_FILE = "prompts/bug_to_user_story_v2.yml"

# Root key used in the YAML file (also the prompt name on the Hub, without the owner)
PROMPT_KEY = "bug_to_user_story_v2"

# Input variable the evaluation dataset provides to the prompt
REQUIRED_INPUT_VARIABLE = "bug_report"


def build_chat_prompt(prompt_data: dict) -> ChatPromptTemplate:
    """
    Build a ChatPromptTemplate from the system/user texts in the YAML.

    Args:
        prompt_data: Prompt data read from the YAML file

    Returns:
        ChatPromptTemplate ready to be serialized and pushed
    """
    messages = [("system", prompt_data["system_prompt"])]

    user_prompt = (prompt_data.get("user_prompt") or "").strip()
    if user_prompt:
        messages.append(("human", prompt_data["user_prompt"]))

    return ChatPromptTemplate.from_messages(messages)


def build_readme(prompt_data: dict) -> str:
    """
    Build the README published alongside the prompt on the Hub.

    Args:
        prompt_data: Prompt data read from the YAML file

    Returns:
        Markdown text describing the prompt and the techniques applied
    """
    techniques = prompt_data.get("techniques_applied") or []
    based_on = prompt_data.get("based_on", "")

    lines = [
        f"# {PROMPT_KEY}",
        "",
        prompt_data.get("description", ""),
        "",
        "## Técnicas de Prompt Engineering aplicadas",
        "",
    ]

    lines.extend(f"- {technique}" for technique in techniques)

    lines.extend(
        [
            "",
            "## Metadados",
            "",
            f"- Versão: {prompt_data.get('version', '')}",
            f"- Criado em: {prompt_data.get('created_at', '')}",
            f"- Variável de entrada: {{{REQUIRED_INPUT_VARIABLE}}}",
        ]
    )

    if based_on:
        lines.append(f"- Baseado em: {based_on}")

    return "\n".join(lines)


def validate_prompt(prompt_data: dict) -> tuple[bool, list]:
    """
    Validate the basic structure of a prompt (simplified version).

    Runs the shared structural checks (required fields, TODOs, minimum number of
    techniques) and adds the checks this challenge depends on: the prompt must
    expose exactly the {bug_report} input variable used by the evaluation dataset.

    Args:
        prompt_data: Prompt data

    Returns:
        (is_valid, errors) - Tuple with the status and the list of errors
    """
    is_valid, errors = validate_prompt_structure(prompt_data)

    user_prompt = (prompt_data.get("user_prompt") or "").strip()
    if not user_prompt:
        errors.append("user_prompt está vazio")

    try:
        input_variables = set(build_chat_prompt(prompt_data).input_variables)
    except Exception as e:
        # Unescaped braces in the texts are the usual cause here
        errors.append(f"Não foi possível montar o ChatPromptTemplate: {e}")
        return (False, errors)

    if input_variables != {REQUIRED_INPUT_VARIABLE}:
        errors.append(
            f"O prompt deve expor apenas a variável '{REQUIRED_INPUT_VARIABLE}', "
            f"encontradas: {sorted(input_variables) or 'nenhuma'}"
        )

    return (len(errors) == 0, errors)


def print_push_error(prompt_name: str, error: Exception) -> None:
    """
    Print an actionable message for the most common push failures.

    Args:
        prompt_name: Identifier in the 'owner/name' format
        error: Exception raised by the push
    """
    message = str(error)
    lowered = message.lower()

    print(f"\n❌ Erro ao fazer push de '{prompt_name}': {error}\n")

    if "handle" in lowered:
        print("Você ainda não criou um handle público no LangSmith.")
        print("Crie em: https://smith.langchain.com/settings")
        print("(Settings > Hub > LangChain Hub Handle)")
    elif "403" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        print("Verifique:")
        print("- LANGSMITH_API_KEY pertence ao workspace do dono do prompt")
        print("- USERNAME_LANGSMITH_HUB corresponde ao seu handle no LangSmith Hub")
    elif "404" in lowered or "not found" in lowered:
        print("Verifique:")
        print(f"- O owner '{prompt_name.split('/')[0]}' é o seu handle no LangSmith Hub")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
    else:
        print("Verifique:")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
        print("- Sua conexão com a internet está funcionando")


def push_prompt_to_langsmith(prompt_name: str, prompt_data: dict) -> bool:
    """
    Push the optimized prompt to the LangSmith Hub (PUBLIC).

    Args:
        prompt_name: Prompt name in the 'owner/name' format
        prompt_data: Prompt data

    Returns:
        True on success, False otherwise
    """
    print(f"\nEnviando prompt para o LangSmith Hub: {prompt_name}")

    chat_prompt = build_chat_prompt(prompt_data)
    tags = list(prompt_data.get("tags") or [])

    try:
        url = hub.push(
            prompt_name,
            chat_prompt,
            new_repo_is_public=True,
            new_repo_description=prompt_data.get("description", ""),
            readme=build_readme(prompt_data),
            tags=tags,
        )
    except Exception as e:
        print_push_error(prompt_name, e)
        return False

    print("   ✓ Push concluído (prompt público)")
    print(f"   ✓ URL: {url}")

    return True


def main():
    """Main entry point"""
    print_section_header("PUSH DE PROMPTS PARA O LANGSMITH HUB")

    if not check_env_vars(["LANGSMITH_API_KEY", "USERNAME_LANGSMITH_HUB"]):
        return 1

    print(f"Lendo prompt otimizado: {PROMPT_FILE}")

    data = load_yaml(PROMPT_FILE)

    if not data or PROMPT_KEY not in data:
        print(f"\n❌ Não foi possível ler '{PROMPT_KEY}' em {PROMPT_FILE}")
        print("\nCertifique-se de que o prompt otimizado existe e está no formato:")
        print(f"   {PROMPT_KEY}:")
        print("     description: ...")
        print("     system_prompt: ...")
        print("     user_prompt: ...")
        return 1

    prompt_data = data[PROMPT_KEY]

    is_valid, errors = validate_prompt(prompt_data)

    if not is_valid:
        print("\n❌ Prompt inválido:")
        for error in errors:
            print(f"   - {error}")
        print(f"\nCorrija {PROMPT_FILE} e execute novamente.")
        return 1

    techniques = prompt_data.get("techniques_applied") or []

    print("   ✓ Prompt válido")
    print(f"   - Versão: {prompt_data.get('version', '')}")
    print(f"   - Técnicas: {', '.join(techniques)}")
    print(f"   - Tags: {', '.join(prompt_data.get('tags') or []) or 'nenhuma'}")
    print(f"   - Tamanho do system_prompt: {len(prompt_data['system_prompt'])} caracteres")
    print(f"   - Tamanho do user_prompt: {len(prompt_data['user_prompt'])} caracteres")

    username = os.getenv("USERNAME_LANGSMITH_HUB")
    prompt_name = f"{username}/{PROMPT_KEY}"

    if not push_prompt_to_langsmith(prompt_name, prompt_data):
        return 1

    print("\n✅ Push concluído com sucesso!")
    print("\nPróximos passos:")
    print("1. Confira o prompt no dashboard: https://smith.langchain.com/prompts")
    print("2. Execute a avaliação: python src/evaluate.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
