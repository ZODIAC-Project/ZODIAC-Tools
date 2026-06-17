workspace "ZODIAC Architecture" "Architecture model for the ZODIAC platform derived from the codebase." {

    !identifiers hierarchical

    model {
        user = person "End User" "Uses the Orion UI to chat with the platform, manage agents, and observe live MQTT-backed workflows."

        llm = softwareSystem "LLM Provider" "External LLM endpoint used by the MCP client for tool-using conversations."
        observability = softwareSystem "Observability Stack" "Prometheus, Grafana, Tempo, Loki, and the OpenTelemetry Collector for metrics, logs, and traces."

        zodiac = softwareSystem "ZODIAC Platform" "Purpose-aware AI and MQTT platform for orchestration, live streams, agent management, and RAG-backed subsidy workflows." {
            ui = container "Orion UI" "Vue 3/Vite frontend for chat, agent control, monitoring links, and broker interaction." "Vue 3, Vite, Nginx"

            mcpClient = container "MCP Client" "HTTP chat endpoint that connects the UI and agent workflows to the MCP server and external LLM." "Python"
            mcpServer = container "PurposeAwareMCP Server" "Purpose-aware tool server exposing MQTT, subscription, agent, and RAG tools over MCP/HTTP." "Python, FastMCP"
            agentApi = container "Agent API" "Creates, lists, and manages agents that call into the MCP client." "Python, FastAPI"
            streamManager = container "Stream Manager" "Manages browser and agent subscriptions to MQTT topics and forwards live events." "Service"

            ragService = container "RAG Service" "FastAPI service for ingesting local data and serving purpose-filtered similarity search results." "Python, FastAPI, ChromaDB"
            ragStore = container "Chroma Data Store" "Embedded persistent vector store used by the RAG service; stores embeddings and purpose-tagged metadata." "ChromaDB, local volume" "Database"

            broker = container "HiveZODIAC Broker" "HiveMQ-based MQTT broker exposing HTTP, MQTT, and WebSocket endpoints." "HiveMQ"
            brokerExtension = container "HivePBAC Extension" "Purpose-based access control extension embedded into the broker runtime; enforces PBAC rules for MQTT subscriptions and publishes." "Java, HiveMQ Extension"

            logCollector = container "Log Collector" "Collects analysis logs from Kubernetes pods for troubleshooting and validation." "Python"
        }

        user -> zodiac.ui "Chats with, manages agents in, and observes the platform via"

        zodiac.ui -> zodiac.mcpClient "Sends chat requests to" "HTTP /chat"
        zodiac.ui -> zodiac.agentApi "Creates and manages agents via" "HTTP"
        zodiac.ui -> zodiac.broker "Observes broker-backed flows via" "WebSocket / MQTT"
        zodiac.ui -> observability "Opens dashboards in" "HTTP"

        zodiac.agentApi -> zodiac.mcpClient "Delegates agent work to" "HTTP /chat"
        zodiac.streamManager -> zodiac.agentApi "Calls agent endpoints to attach live subscriptions" "HTTP"
        zodiac.streamManager -> zodiac.broker "Subscribes to and forwards live topic traffic from" "MQTT"

        zodiac.mcpClient -> zodiac.mcpServer "Uses tools from" "MCP over HTTP"
        zodiac.mcpClient -> llm "Requests completions from" "HTTP"
        zodiac.mcpClient -> observability "Exports telemetry to" "OTLP"

        zodiac.mcpServer -> zodiac.broker "Publishes, subscribes, and reserves purpose-aware topics in" "MQTT / HTTP"
        zodiac.mcpServer -> zodiac.streamManager "Creates stream subscriptions in" "HTTP"
        zodiac.mcpServer -> zodiac.agentApi "Creates and inspects agents in" "HTTP"
        zodiac.mcpServer -> zodiac.ragService "Queries and ingests knowledge in" "HTTP"
        zodiac.mcpServer -> observability "Exports telemetry to" "OTLP"

        zodiac.ragService -> zodiac.ragStore "Reads and writes vectors and purpose metadata in"

        zodiac.brokerExtension -> zodiac.broker "Runs inside"
        zodiac.logCollector -> observability "Publishes collected operational data to" "Logs / analysis outputs"
        zodiac.logCollector -> zodiac.agentApi "Observes runtime behavior of" "Kubernetes logs"
        zodiac.logCollector -> zodiac.mcpClient "Observes runtime behavior of" "Kubernetes logs"
        zodiac.logCollector -> zodiac.mcpServer "Observes runtime behavior of" "Kubernetes logs"
    }

    views {
        systemContext zodiac "system-context" "System context for the ZODIAC platform." {
            include *
            autoLayout lr
        }

        container zodiac "containers" "Container view for the ZODIAC platform." {
            include user
            include llm
            include observability
            include zodiac.ui
            include zodiac.mcpClient
            include zodiac.mcpServer
            include zodiac.agentApi
            include zodiac.streamManager
            include zodiac.ragService
            include zodiac.ragStore
            include zodiac.broker
            include zodiac.brokerExtension
            include zodiac.logCollector
            autoLayout lr
        }

        styles {
            element "Person" {
                background #ffffff
                color #0b5fff
                stroke #0b5fff
                strokeWidth 2
                shape person
            }
            element "Software System" {
                background #ffffff
                color #1168bd
                stroke #1168bd
                strokeWidth 2
            }
            element "Container" {
                background #ffffff
                color #438dd5
                stroke #438dd5
                strokeWidth 2
            }
            element "Database" {
                shape cylinder
            }
        }

        theme default
    }
}
