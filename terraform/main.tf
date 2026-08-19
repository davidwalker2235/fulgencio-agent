resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  resource_name = "${var.name_prefix}-${random_string.suffix.result}"
  agent_image   = "${azurerm_container_registry.main.login_server}/${var.image_name}"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.resource_name}"
  location = var.location
}

resource "azurerm_container_registry" "main" {
  name                = replace("acr${local.resource_name}", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.resource_name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.resource_name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_container_app" "main" {
  name                         = "ca-${local.resource_name}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }
  secret {
    name  = "azure-openai-api-key"
    value = var.azure_openai_api_key
  }
  secret {
    name  = "litellm-master-key"
    value = var.litellm_master_key
  }
  secret {
    name  = "firebase-service-account"
    value = var.firebase_service_account_json
  }
  secret {
    name  = "azure-sql-connection"
    value = var.azure_sql_connection_string
  }
  secret {
    name  = "ws-basic-username"
    value = var.ws_basic_username
  }
  secret {
    name  = "ws-basic-password"
    value = var.ws_basic_password
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "agent"
      image  = local.agent_image
      cpu    = 0.75
      memory = "1.5Gi"

      env {
        name  = "MODEL_NAME"
        value = "gpt-realtime-1.5"
      }
      env {
        name  = "LITELLM_PROXY_HTTP_URL"
        value = "http://localhost:4000"
      }
      env {
        name  = "LITELLM_PROXY_WS_URL"
        value = "ws://localhost:4000"
      }
      env {
        name        = "LITELLM_PROXY_API_KEY"
        secret_name = "litellm-master-key"
      }
      env {
        name  = "FIREBASE_DATABASE_URL"
        value = var.firebase_database_url
      }
      env {
        name        = "FIREBASE_SERVICE_ACCOUNT_JSON"
        secret_name = "firebase-service-account"
      }
      env {
        name        = "AZURE_SQL_CONNECTION_STRING"
        secret_name = "azure-sql-connection"
      }
      env {
        name        = "WS_BASIC_USERNAME"
        secret_name = "ws-basic-username"
      }
      env {
        name        = "WS_BASIC_PASSWORD"
        secret_name = "ws-basic-password"
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/live"
        initial_delay           = 10
        interval_seconds        = 20
        timeout                 = 3
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/ready"
        interval_seconds        = 10
        timeout                 = 10
        failure_count_threshold = 10
      }
    }

    container {
      name    = "litellm"
      image   = local.agent_image
      command = ["python"]
      args    = ["/app/run_litellm_proxy.py"]
      cpu     = 0.75
      memory  = "1.5Gi"

      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = var.azure_openai_endpoint
      }
      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "azure-openai-api-key"
      }
      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = var.azure_openai_api_version
      }
      env {
        name        = "LITELLM_MASTER_KEY"
        secret_name = "litellm-master-key"
      }
      env {
        name  = "LITELLM_HOST"
        value = "0.0.0.0"
      }
      env {
        name  = "LITELLM_PORT"
        value = "4000"
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 4000
        path                    = "/health/liveliness"
        initial_delay           = 20
        interval_seconds        = 20
        timeout                 = 3
        failure_count_threshold = 3
      }
    }
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}
