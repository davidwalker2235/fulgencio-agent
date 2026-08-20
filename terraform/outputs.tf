output "resource_group_name" {
  value = data.azurerm_resource_group.main.name
}

output "acr_name" {
  value = data.azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = data.azurerm_container_registry.main.login_server
}

output "fqdn" {
  value = azurerm_container_app.main.ingress[0].fqdn
}

output "websocket_url_without_credentials" {
  value = "wss://${azurerm_container_app.main.ingress[0].fqdn}/ws"
}
