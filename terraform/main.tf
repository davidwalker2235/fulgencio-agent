data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

data "azurerm_container_registry" "main" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.main.name
}

data "azurerm_container_app_environment" "main" {
  name                = var.environment_name
  resource_group_name = data.azurerm_resource_group.main.name
}

data "azurerm_user_assigned_identity" "main" {
  name                = var.identity_name
  resource_group_name = data.azurerm_resource_group.main.name
}

locals {
  agent_image = "${data.azurerm_container_registry.main.login_server}/${var.image_name}"
}

resource "azurerm_container_app" "main" {
  name                         = var.container_app_name
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.main.id]
  }

  registry {
    server   = data.azurerm_container_registry.main.login_server
    identity = data.azurerm_user_assigned_identity.main.id
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
