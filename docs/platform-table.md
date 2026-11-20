# The builder table

The 64 cells of the paper's table of eight shared agent builders: for each builder and each
pattern, what the documented default allows. The four open-source builders were read from their
source code and the four commercial ones from the vendors' documentation, as they stood on
11 November 2026. Commercial products were not tested. Every cell gives the reason for its code and
the file or page it rests on.

| Code | Meaning |
|---|---|
| F | feasible by default |
| F† | feasible, but a default confirmation asks the runner first |
| P | needs a setting, or an action by an admin |
| M | a documented default prevents it |
| ? | undocumented |

A code describes a workspace in which the builder is switched on and its ordinary connectors are
in use. Where an admin must first enable the builder as a whole, the reason says so and the code
is unchanged. P is for a further setting, or for an admin action on the co-author's own tool,
server or agent. Steer asks whose credentials a run spends; Implant and Relay ask only whether the
text arrives or its author is lost at the hop.

| Builder | Steer | Implant | Relay | Sinkhole | Widen | Swap | Promote | Watch |
|---|---|---|---|---|---|---|---|---|
| n8n | P | F | F | F | F | F | F | F |
| Dify | P | F | F | F | F | F | F | F |
| Flowise | P | F | F | F | F | F | F | F |
| Langflow | P | F | F | F | F | F | F | F |
| Copilot Studio | F | F | F | F | F | F | M | F |
| Gemini Enterprise | F† | F | P | P | F† | F | ? | P |
| ChatGPT Enterprise | F† | F | ? | P | F | F | F | F |
| Claude Team/Enterprise | F | F | ? | P | F | F | ? | F |

The runner is the user who starts a shared workflow. Patterns: Steer, a co-author's text makes
the agent act with the runner's credentials. Implant, text in shared memory or knowledge steers a
later run by another user. Relay, instructions pass through another agent and their author is
lost. Sinkhole, a tool or agent the co-author owns receives the runner's data. Widen, the runner's
data is written where the co-author can read it. Swap, the workflow, skill or tool changes after
the runner agreed to it. Promote, memory consolidation lifts the runner's facts to a shared tier.
Watch, someone other than the runner (an owner, editor or admin) can read the runner's
conversations with nothing to enable first.

## n8n

Source: https://github.com/n8n-io/n8n at commit `d48891758396576dc1d835d48a7f7e4be15f2684`. Paths are relative to the repository root.

Record of who wrote an instruction: each saved version stores its authors as one string; nothing is recorded per node or field.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | P | A shared or published workflow runs with the credentials stored on the workflow; the acting user is not consulted. Per-runner credentials are a licensed Enterprise feature, and a separate runtime-credentials module is off unless a flag is set. | `packages/cli/src/executions/pre-execution-checks/credentials-permission-checker.ts:323-328`, `packages/cli/src/modules/dynamic-credentials.ee/dynamic-credentials.module.ts:16`, `packages/cli/src/modules/dynamic-credentials.ee/services/dynamic-credential.service.ts:77-80` |
| Implant | F | Editors can place text in shared persistent context that later runs read: memory under a static key, project data tables and vector stores. | `packages/@n8n/nodes-langchain/nodes/memory/descriptions.ts:16-18`, `packages/@n8n/nodes-langchain/nodes/memory/MemoryBufferWindow/MemoryBufferWindow.node.ts:177` |
| Relay | F | Agent-as-tool, sub-workflow and MCP hops carry no record of who wrote an instruction, and the MCP server trigger's bearer or header secret does not distinguish the original caller. | `packages/@n8n/db/src/entities/workflow-history.ts:26-27`, `packages/@n8n/nodes-langchain/nodes/mcp/McpTrigger/McpTrigger.node.ts:154-157`, `packages/@n8n/nodes-langchain/nodes/tools/ToolWorkflow/v2/utils/WorkflowToolService.ts:286` |
| Sinkhole | F | The author points MCP client, HTTP or external memory nodes at any URL or store, with credentials of their choosing, and a caller's inputs flow there. | `packages/@n8n/nodes-langchain/nodes/mcp/McpClientTool/McpClientTool.node.ts:101-102`, `packages/@n8n/nodes-langchain/nodes/trigger/ChatTrigger/ChatTrigger.node.ts:500-504`, `packages/cli/src/modules/type-availability-policies/type-availability-policies.module.ts:17-20` |
| Widen | F | Chat history lands in external memory stores and data tables the builder chose, and executions with full node input and output are saved by default where project members can read them. | `packages/@n8n/config/src/configs/executions.config.ts:154,158,171`, `packages/@n8n/permissions/src/roles/scopes/project-scopes.ee.ts:49,132,193,252` |
| Swap | F | Anyone who may publish can republish; callers always run the currently published version, with no pin and no notice. | `packages/cli/src/workflow-execute-additional-data.ts:203-205`, `packages/cli/src/modules/workflow-reviews.ee/workflow-reviews.module.ts:8` |
| Promote | F | Memory nodes with a shared key and project data tables let one runner's content become context for other runners of the same workflow. | `packages/@n8n/nodes-langchain/nodes/memory/descriptions.ts:21`, `packages/cli/src/modules/agents/utils/agent-memory-scope.ts:2-3` |
| Watch | F | Saved executions, with inputs and outputs, are readable by the workflow's owner and project members. | `packages/@n8n/permissions/src/roles/scopes/project-scopes.ee.ts:49,132,193,252`, `packages/cli/src/modules/redaction/executions/execution-redaction.service.ts:443` |

## Dify

Source: https://github.com/langgenius/dify at commit `6d3447e8c34f2232c3a41838c9ffdb5ca442a19a`. Paths are relative to the repository root.

Record of who wrote an instruction: the workflow stores who created and last updated it and who published each version; nothing per node or prompt field.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | P | Tool credentials are looked up by workspace and credential, never by the end user, and there is no end-user sign-in for tools; forwarding a caller's identity to an MCP server is an Enterprise option that is off by default. | `api/core/tools/tool_manager.py:253-258`, `api/repositories/credentials/query_repository.py:77-82`, `api/models/tools.py:343` |
| Implant | F | Editors add documents to shared knowledge bases and set conversation variables that later runs by other users read. | `api/core/rag/retrieval/dataset_retrieval.py:2116-2118`, `api/core/app/features/annotation_reply/annotation_reply.py:36-42` |
| Relay | F | Workflow-as-tool, agents inside workflows, plugin calls into an app and app-as-MCP-server chain apps; the MCP server maps every caller to one end user, so the original caller is lost. | `api/controllers/mcp/mcp.py:303-306`, `api/controllers/inner_api/plugin/plugin.py:477`, `api/core/plugin/backwards_invocation/app.py:249-271,283` |
| Sinkhole | F | An editor can send an app's traces, with runners' inputs and outputs, to an external tracing service at a host the editor sets, and can add HTTP nodes, custom tools or MCP servers that point at any endpoint. | `api/controllers/console/app/ops_trace.py:44-50,183-186`, `api/services/tracing/providers.py:22-33`, `api/pyproject.toml:125` |
| Widen | F | Conversations and workflow runs, with inputs and outputs, are stored where workspace members with access to the app can read them. | `api/controllers/console/app/conversation.py:98,143,202,247` |
| Swap | F | Any editor can publish, and web app, API and MCP consumers get the latest published version with no notice. A service-API caller can pin a version, but the default path is unpinned. | `api/controllers/console/app/workflow.py:1344-1355`, `api/controllers/service_api/app/workflow.py:403,462-464`, `api/services/app_generate_service.py:496-497` |
| Promote | F | An editor can create an API key scoped to one knowledge base and write documents into it, so a flow can lift a runner's content into shared knowledge without an owner or admin. | `api/controllers/console/datasets/datasets.py:765-767,778-780`, `api/controllers/console/apikey.py:33,32`, `api/services/knowledge/api_key_service.py:82-85` |
| Watch | F | Workspace members with access to the app read its conversation logs, including other users' messages. | `api/controllers/console/app/conversation.py:98,143,202,247` |

## Flowise

Source: https://github.com/FlowiseAI/Flowise at commit `9291856d1ea4a4ceea9f8fef8ce14f4f6c81e8eb`. Paths are relative to the repository root.

Record of who wrote an instruction: none. Flows, tools and credentials have no author column, and there is no version history.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | P | A credential has no user and is looked up by id alone, and the open-source edition has a single owner, so a flow runs on the maker's credentials. A caller can supply its own values only where the flow's owner has switched on overrides, which are off by default. | `packages/server/src/database/entities/Credential.ts:6-29`, `packages/components/src/utils.ts:663-665`, `packages/server/src/enterprise/services/account.service.ts:189-192` |
| Implant | F | Author-written content in shared document stores, variables, shared memory or a fixed session id steers later runs by other users. | `packages/server/src/utils/index.ts:1831-1846` |
| Relay | F | A flow called as a tool or sub-flow is reached over the prediction API with at most a flow API key, so neither the original user nor the instruction chain crosses the hop. | `packages/components/nodes/agentflow/ExecuteFlow/ExecuteFlow.ts:195-197` |
| Sinkhole | F | The author adds custom tools, MCP servers or HTTP nodes pointing at any endpoint, and callers' inputs flow there. | `packages/components/nodes/tools/MCP/CustomMCP/CustomMCP.ts:176-187` |
| Widen | F | Callers' chats, with tool use and uploads, are stored for the flow's owner, shared memory is the default, and flows can write into shared document stores. | `packages/server/src/routes/chat-messages/index.ts:11-14` |
| Swap | F | There is no version history and no draft: saving overwrites the flow that embeds, the API and MCP endpoints run at once, with no notice. | `packages/server/src/services/chatflows/index.ts:492`, `packages/components/nodes/tools/CustomTool/CustomTool.ts:108` |
| Promote | F | Memory keyed by a shared or fixed session id pools content from different callers into one store that later runs read. | `packages/components/nodes/memory/Mem0/Mem0.ts:59,68` |
| Watch | F | Whoever may view the flow reads every caller's full conversation. | `packages/server/src/routes/chat-messages/index.ts:11-14`, `packages/server/src/services/executions/index.ts:50` |

## Langflow

Source: https://github.com/langflow-ai/langflow at commit `71b28b924050c95a244227d5a1424f2495014e14`. Paths are relative to the repository root.

Record of who wrote an instruction: each saved version records the user who created it; nothing per prompt field.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | P | The settings that make it feasible: a flow marked public can be built by any signed-in user on that user's own variables, and a request can carry its own variable values in headers. Without them a private flow can be read and run only by its owner, and sharing with another signed-in user needs an authorization plugin that the open-source build does not ship. | `src/lfx/src/lfx/services/authorization/base.py:337`, `src/lfx/src/lfx/services/settings/auth.py:294-296`, `src/backend/base/langflow/services/authorization/service.py:20-21` |
| Implant | F | The owner's knowledge bases and memory, read by the owner's flows, carry author-placed text into later runs made with the owner's key, by webhook or through a public MCP project. | `src/backend/base/langflow/api/utils/flow_utils.py:356`, `src/backend/base/langflow/services/authorization/public_access.py:82-87`, `src/backend/base/langflow/api/v1/chat.py:1281` |
| Relay | F | Run-flow and flow-as-tool, the A2A client and server, and MCP chain flows; an inbound A2A call is anonymous or the owner, and a public MCP project runs as its owner, so the original caller is lost. | `src/lfx/src/lfx/components/models_and_agents/a2a_agent.py:187`, `src/backend/base/langflow/api/v1/mcp_projects.py:151-158`, `src/backend/base/langflow/api/v1/a2a.py:137` |
| Sinkhole | F | The author embeds an MCP server, an A2A agent address or an HTTP component pointing at an endpoint they run, and callers' inputs flow there. | `src/lfx/src/lfx/utils/flow_validation.py:2025-2026`, `src/lfx/src/lfx/components/models_and_agents/a2a_agent.py:360` |
| Widen | F | Runs that execute as the owner write callers' data into the owner's knowledge base and memory, and the owner can read those sessions' messages. | `src/backend/base/langflow/api/v1/endpoints.py:651-653` |
| Swap | F | There is no draft: the public link, API, webhook, MCP and A2A run the latest saved flow at once, with no pin and no notice. | `src/backend/base/langflow/services/database/models/flow_version/model.py:19-40` |
| Promote | F | The owner's memory captures content from callers' runs automatically and serves it to later runs. | `src/backend/base/langflow/services/database/models/memory_base/model.py:15`, `src/lfx/src/lfx/components/files_and_knowledge/memory_retrieval.py:108-115`, `src/lfx/src/lfx/services/settings/groups/security.py:335,349` |
| Watch | F | The flow's owner reads the messages of runs made through the owner's key, webhook or serving route. | `src/backend/base/langflow/api/v1/monitor.py:331-333`, `src/backend/base/langflow/services/database/models/flow/model.py:278-279` |

Checked on 11 November 2026 on a local install of the open-source build (version 1.13.1,
sign-in required, two regular users, each with their own API key): the second user gets HTTP
404 both reading and running the first user's flow, where the owner gets 200, and the flow
does not appear in the second user's list.

## Copilot Studio

Source: the vendor's documentation. Each cell links the page it rests on.

Record of who wrote an instruction: the editor shows who is working on a topic now, and admin audit events record that a component was updated; no version history of instructions and no author per line is documented.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | F | A new tool uses the end user's credentials by default and does not ask before it runs, and a co-author can edit the agent's instructions and publish. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-tools-custom-agent, https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-connectors |
| Implant | F | Any co-author can add knowledge sources and skills that steer later runs by every user the agent is shared with. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-share-bots, https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/skills-overview |
| Relay | F | Child, connected and A2A agents run their own orchestration; an A2A call sends the full chat history, and nothing carries who wrote an instruction across the hop. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents, https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-agent-to-agent |
| Sinkhole | F | A maker adds any MCP server or A2A agent, so an endpoint the author controls receives runners' inputs. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-agent-agent-to-agent, https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp |
| Widen | F | Maker-provided credentials are enabled by default alongside end-user ones, so tools and flows can write runner data into services the maker controls. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-no-maker-authentication, https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-sharing-controls-limits |
| Swap | F | Any co-author can publish, and users get the new version on their next message; changes to an MCP server's tools appear without a publish step. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/publication-fundamentals-publish-channels, https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp |
| Promote | M | The documented memory is kept per user and per agent and is not shared between users. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/memory-overview |
| Watch | F | Makers with access to the agent, its owners and editors included, can view and download transcripts by default. | https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-transcript-controls, https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-transcripts-studio |

## Gemini Enterprise

Source: the vendor's documentation. Each cell links the page it rests on.

Record of who wrote an instruction: workflows have a version history (save, compare, restore) that does not say who edited; an admin can turn on audit logs that record an update to an agent.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | F† | Connectors act under each runner's own account, and a shared workflow is read-only for the people it is shared with, so the owner's text drives them. An action that modifies external data needs the runner's approval, except mail or calendar events sent to oneself; approval for chat agents is not documented. | https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/share-workflows, https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/workflows |
| Implant | F | The owner's knowledge files and skills steer the runs of everyone the agent is shared with. | https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/share-agent |
| Relay | P | A2A agents are registered by an admin; once registered, a workflow can call them and nothing carries who wrote an instruction across the hop. | https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent, https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/add-existing-agents |
| Sinkhole | P | Only admins add custom MCP data stores and A2A agents, so an author-owned endpoint needs an admin action. | https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server, https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/connect-mcp-servers |
| Widen | F† | A shared workflow can write the runner's data to a place the owner can read through the runner's own connector, with the same approval step as Steer. | https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/share-workflows |
| Swap | F | When the owner turns on a new version, all shared users run it on their next execution; only the first share is reviewed. | https://docs.cloud.google.com/gemini/enterprise/docs/workflow-builder/share-workflows |
| Promote | ? | Saved memory is described per user; no shared tier is documented. | https://docs.cloud.google.com/gemini/enterprise/docs/configure-personalization |
| Watch | P | Shared users see only their own runs; admins see runs in audit logs once logging is turned on, and prompt content only with a further setting. | https://docs.cloud.google.com/gemini/enterprise/docs/set-up-usage-audit-logs |

## ChatGPT Enterprise

Source: the vendor's documentation. Each cell links the page it rests on.

Record of who wrote an instruction: workspace agents and GPTs have a version history that does not show who made a change; the Compliance API gives admins an audit log of changes to each agent.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | F† | An editor of a workspace agent can change its instructions and publish, and the agent's builder chooses, per app connection, whether it uses each runner's own account. Write actions ask the runner by default, but the agent's builder or an editor can set some apps to never ask. An admin must first have enabled workspace agents and the app's write actions. | https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business, https://help.openai.com/en/articles/11509118-admin-controls-security-and-compliance-for-plugins-and-apps |
| Implant | F | Collaborators who can edit a shared project or agent change the instructions and files that other members' chats use. | https://help.openai.com/en/articles/10169521-projects-in-chatgpt |
| Relay | ? | Chaining one workspace agent to another is not documented. | https://learn.chatgpt.com/workspace-agents/trigger-runs |
| Sinkhole | P | Custom GPT actions, which let a builder call any endpoint, are being retired and are not migrated; other routes to an author-owned endpoint need an admin to enable an app or server. | https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq, https://learn.chatgpt.com/docs/enterprise/gpts-and-sharing |
| Widen | F | Shared projects are on by default, and every member sees the chats and files that another member's run adds to one, with no connector write and so no confirmation. A write through an agent-owned or workspace connection is a second route, which asks first by default. | https://learn.chatgpt.com/docs/enterprise/shared-connections |
| Swap | F | An editor publishes a new version of an agent, or updates a GPT, for everyone; no notice to users and no way to stay on the old version is documented. | https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business |
| Promote | F | Shared projects are on by default and use one project-wide memory, so what one member adds can shape answers that other members see. | https://help.openai.com/en/articles/10169521-projects-in-chatgpt |
| Watch | F | In a shared project every member can view the project's chats and files; admins can also read conversations through the Compliance API. | https://help.openai.com/en/articles/10169521-projects-in-chatgpt, https://learn.chatgpt.com/docs/enterprise/work-admin-faq |

## Claude Team/Enterprise

Source: the vendor's documentation. Each cell links the page it rests on.

Record of who wrote an instruction: no version history of project instructions is documented and the audit log has no event for an instruction edit; skills published to the organization keep a version history.

| Pattern | Code | Reason | Where |
|---|---|---|---|
| Steer | F | Members connect each connector with their own account, and the text of a shared skill or project steers those connectors. The documentation says that Claude can ask before a connector tool runs and that the user can choose to always allow a tool; it states no default, so no default confirmation is coded. An owner can set tools to always allow, and Research mode runs tools without asking. An owner adds each connector for the organization. | https://claude.com/docs/connectors/getting-started, https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities |
| Implant | F | Members who can edit a shared project change the instructions and knowledge that other members' chats use, and a shared skill updates for everyone at next use. | https://support.claude.com/en/articles/9519177-how-can-i-create-and-manage-projects |
| Relay | ? | No agent-to-agent hop across users is documented. | https://claude.com/docs/plugins/overview |
| Sinkhole | P | Only owners add connectors for the organization, so an author-owned endpoint needs an owner's action. | https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp, https://claude.com/docs/plugins/overview |
| Widen | F | A shared skill can direct the runner's own connector to write the runner's data to a place the co-author can read; Claude can ask first, as for Steer, with no documented default. | https://support.claude.com/en/articles/9519189-manage-project-visibility-and-sharing |
| Swap | F | When the owner of a shared skill saves a new version, everyone it is shared with gets it at next use; edits to a shared project's instructions apply at once. | https://support.claude.com/en/articles/13119606-provisioning-and-managing-skills-for-your-organization, https://claude.com/docs/plugins/overview |
| Promote | ? | Each project has its own memory, but whether it is shared across members is not documented. | https://support.claude.com/en/articles/11817273-use-claudes-chat-search-and-memory-to-build-on-previous-context |
| Watch | F | The Primary Owner can export the organization's data, conversations included, with no setting to enable first. Chats in a shared project stay private to their author. | https://support.claude.com/en/articles/13346720-export-your-organization-s-data, https://platform.claude.com/docs/en/manage-claude/compliance-api-access |

