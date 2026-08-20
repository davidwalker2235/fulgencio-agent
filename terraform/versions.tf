terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.13.0"
    }
  }

  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}
