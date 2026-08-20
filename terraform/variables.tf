variable "resource_group_name" {
  type        = string
  description = "Resource Group existente que aloja Fulgencio."
  default     = "fulgencio-rg"
}

variable "acr_name" {
  type        = string
  description = "ACR existente compartido con fulgencio-project."
  default     = "fulgencioacr"
}

variable "environment_name" {
  type        = string
  description = "Container Apps Environment existente."
  default     = "fulgencio-env"
}

variable "identity_name" {
  type        = string
  description = "Identidad administrada existente con AcrPull."
  default     = "fulgencio-identity"
}

variable "container_app_name" {
  type        = string
  description = "Nombre de la nueva Container App."
  default     = "fulgencio-agent"
}

variable "location" {
  type        = string
  description = "Solo informativo para documentación local."
  default     = "West Europe"
}

variable "image_name" {
  type        = string
  description = "Repositorio y etiqueta de la imagen dentro de ACR."
  default     = "fulgencio-agent:latest"
}

variable "azure_openai_endpoint" {
  type      = string
  sensitive = true
}

variable "azure_openai_api_key" {
  type      = string
  sensitive = true
}

variable "azure_openai_api_version" {
  type    = string
  default = "2024-10-01-preview"
}

variable "litellm_master_key" {
  type      = string
  sensitive = true
}

variable "firebase_database_url" {
  type      = string
  sensitive = true
}

variable "firebase_service_account_json" {
  type      = string
  sensitive = true
}

variable "azure_sql_connection_string" {
  type      = string
  sensitive = true
}

variable "ws_basic_username" {
  type      = string
  sensitive = true
}

variable "ws_basic_password" {
  type      = string
  sensitive = true
}
