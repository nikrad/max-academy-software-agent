import chainlit as cl
import os
import json

from helpers import dprint


class Agent:
    """
    Base class for all agents.
    """

    tools = [
        {
            "type": "function",
            "function": {
                "name": "updateArtifact",
                "description": "Update an artifact file which is HTML, CSS, or markdown with the given contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The name of the file to update.",
                        },
                        "contents": {
                            "type": "string",
                            "description": "The markdown, HTML, or CSS contents to write to the file.",
                        },
                    },
                    "required": ["filename", "contents"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "callAgent",
                "description": "Instantiates an agent with the given name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_type": {
                            "type": "string",
                            "description": "The name of the agent to instantiate. Currently, the only supported agent is named 'implementation'.",
                        },
                    },
                    "required": ["agent_type"],
                    "additionalProperties": False,
                },
            },
        },
    ]

    def __init__(self, name, client, prompt="", agents={}, gen_kwargs=None):
        self.name = name
        self.client = client
        self.prompt = prompt
        self.gen_kwargs = gen_kwargs or {"model": "gpt-4o", "temperature": 0.2}
        self.agents = agents

    async def execute(self, message_history):
        """
        Executes the agent's main functionality.

        Note: probably shouldn't couple this with chainlit, but this is just a prototype.
        """
        copied_message_history = message_history.copy()

        # Check if the first message is a system prompt
        if copied_message_history and copied_message_history[0]["role"] == "system":
            # Replace the system prompt with the agent's prompt
            copied_message_history[0] = {
                "role": "system",
                "content": self._build_system_prompt(),
            }
        else:
            # Insert the agent's prompt at the beginning
            copied_message_history.insert(
                0, {"role": "system", "content": self._build_system_prompt()}
            )

        response_message = cl.Message(content="")
        await response_message.send()

        dprint(f"Executing {self.name}")

        stream = await self.client.chat.completions.create(
            messages=copied_message_history,
            stream=True,
            tools=self.tools,
            tool_choice="auto",
            **self.gen_kwargs,
        )

        fn_calls = []
        async for part in stream:
            delta = part.choices[0].delta
            # dprint(delta)
            if delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    if not tool_call_chunk.function:
                        continue
                    if len(fn_calls) <= tool_call_chunk.index:
                        fn_calls.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )
                    fn_call = fn_calls[tool_call_chunk.index]
                    if tool_call_chunk.id:
                        fn_call["id"] += tool_call_chunk.id
                    if tool_call_chunk.function.name:
                        fn_call["function"]["name"] += tool_call_chunk.function.name
                    if tool_call_chunk.function.arguments:
                        fn_call["function"][
                            "arguments"
                        ] += tool_call_chunk.function.arguments

            if token := part.choices[0].delta.content or "":
                await response_message.stream_token(token)

        if len(fn_calls):
            dprint("fn_calls:", len(fn_calls))
            is_file_update = False
            for fn_call in fn_calls:
                fn_name = fn_call["function"]["name"]
                arguments = fn_call["function"]["arguments"]
                arguments_dict = json.loads(arguments)
                if fn_name == "callAgent":
                    agent_name = arguments_dict.get("agent_type")
                    dprint("callAgent():", agent_name)
                    if agent_name and agent_name in self.agents:
                        await self.agents[agent_name].execute(copied_message_history)

                elif fn_name == "updateArtifact":
                    is_file_update = True
                    filename = arguments_dict.get("filename")
                    contents = arguments_dict.get("contents")
                    dprint("updateArtifact():", filename)

                    if filename and contents:
                        os.makedirs("artifacts", exist_ok=True)
                        with open(os.path.join("artifacts", filename), "w") as file:
                            file.write(contents)

                        # Add a message to the message history
                        message_history.append(
                            {
                                "role": "system",
                                "content": f"The artifact '{filename}' was updated.",
                            }
                        )

            if is_file_update:
                dprint(
                    f"{self.name} is calling chat completion after updateArtifact() call(s)"
                )
                copied_message_history = message_history.copy()
                copied_message_history.append(
                    {
                        "role": "system",
                        "content": self._build_system_prompt(),
                    }
                )

                stream = await self.client.chat.completions.create(
                    messages=copied_message_history, stream=True, **self.gen_kwargs
                )
                await response_message.stream_token("\n\n")
                async for part in stream:
                    if token := part.choices[0].delta.content or "":
                        await response_message.stream_token(token)

        else:
            dprint("No tool call")

        await response_message.update()

        return response_message.content

    def _build_system_prompt(self):
        """
        Builds the system prompt including the agent's prompt and the contents of the artifacts folder.
        """
        artifacts_content = "<ARTIFACTS>\n"
        artifacts_dir = "artifacts"

        if os.path.exists(artifacts_dir) and os.path.isdir(artifacts_dir):
            for filename in os.listdir(artifacts_dir):
                file_path = os.path.join(artifacts_dir, filename)
                if os.path.isfile(file_path):
                    with open(file_path, "r") as file:
                        file_content = file.read()
                        artifacts_content += (
                            f"<FILE name='{filename}'>\n{file_content}\n</FILE>\n"
                        )

        artifacts_content += "</ARTIFACTS>"

        return f"{self.prompt}\n{artifacts_content}"
