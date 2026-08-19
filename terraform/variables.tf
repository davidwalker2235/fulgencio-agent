variable "name_prefix" {
  type        = string
  description = "Prefijo corto y único para los recursos."
  default     = "fulgencio-agent"
}

variable "location" {
  type        = string
  description = "Región de Azure."
  default     = "westeurope"
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

