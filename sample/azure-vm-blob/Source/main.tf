# https://dev.to/holger/test-azure-bastion-deployment-via-terraform-18o8
# Bastion Linux VM Input Variables
variable "bastion_service_subnet_name" {
  description = "Bastion Service Subnet Name"
  default = "AzureBastionSubnet"
}

variable "bastion_service_address_prefixes" {
  description = "Bastion Service Address Prefixes"
  default = ["10.0.101.0/27"]
}

# ---------------------------------------

# Terraform Block
terraform {
  required_version = ">= 1.0.0"
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      version = ">= 2.0" 
    }
    random = {
      source = "hashicorp/random"
      version = ">= 3.0"
    }
    null = {
      source = "hashicorp/null"
      version = ">= 3.0"
    }     
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = "example"
  location = "West Europe"
}

# ---------------------------------------
# VPC & Subnets

# Create virtual network
resource "azurerm_virtual_network" "vnet" {
  name                = "test-vnet"
  address_space       = ["10.40.2.0/24"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

# Create subnets
resource "azurerm_subnet" "bastion_subnet" {
  name                 = "bastion-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.40.2.0/25"]
}

resource "azurerm_subnet" "vm_subnet" {
  name                 = "vm-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.40.2.128/25"]
}


# ---------------------------------------
# Security Group for private subnet

# Create Network Security Group for VM Subnet and the corresponding rule for RDP from Azure Bastion
resource "azurerm_network_security_group" "vm_subnet_nsg" {
  name                = "nsg-vm-subnet"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

# Allow RDP, SSH from bastion -> private subnet or inside subnet, otherwise block

resource "azurerm_network_security_rule" "inbound_allow_rdp" {
  network_security_group_name = azurerm_network_security_group.vm_subnet_nsg.name
  resource_group_name         = azurerm_resource_group.rg.name
  name                        = "Inbound_Allow_Bastion_RDP"
  priority                    = 500
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "3389"
  source_address_prefix       = azurerm_subnet.bastion_subnet.address_prefixes[0]
  destination_address_prefix  = azurerm_subnet.vm_subnet.address_prefixes[0]
}

resource "azurerm_network_security_rule" "inbound_allow_ssh" {
  network_security_group_name = azurerm_network_security_group.vm_subnet_nsg.name
  resource_group_name         = azurerm_resource_group.rg.name
  name                        = "Inbound_Allow_Bastion_SSH"
  priority                    = 510
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = azurerm_subnet.bastion_subnet.address_prefixes[0]
  destination_address_prefix  = azurerm_subnet.vm_subnet.address_prefixes[0]
}

resource "azurerm_network_security_rule" "inbound_deny_all" {
  network_security_group_name = azurerm_network_security_group.vm_subnet_nsg.name
  resource_group_name         = azurerm_resource_group.rg.name
  name                        = "Inbound_Deny_Any_Any"
  priority                    = 1000
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = azurerm_subnet.vm_subnet.address_prefixes[0]
}

resource "azurerm_network_security_rule" "outbound_allow_subnet" {
  network_security_group_name = azurerm_network_security_group.vm_subnet_nsg.name
  resource_group_name         = azurerm_resource_group.rg.name
  name                        = "Outbound_Allow_Subnet_Any"
  priority                    = 500
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = azurerm_subnet.vm_subnet.address_prefixes[0]
  destination_address_prefix  = azurerm_subnet.vm_subnet.address_prefixes[0]
}

resource "azurerm_network_security_rule" "outbound_deny_all" {
  network_security_group_name = azurerm_network_security_group.vm_subnet_nsg.name
  resource_group_name         = azurerm_resource_group.rg.name
  name                        = "Outbound_Deny_Any_Any"
  priority                    = 1000
  direction                   = "Outbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = azurerm_subnet.vm_subnet.address_prefixes[0]
  destination_address_prefix  = "*"
}

resource "azurerm_subnet_network_security_group_association" "nsg_vm_subnet_association" {
  network_security_group_id = azurerm_network_security_group.vm_subnet_nsg.id
  subnet_id                 = azurerm_subnet.vm_subnet.id
}



# ---------------------------------------
# Network interface (~ Route table + Route table assoc in AWS)

# For private subnet
resource "azurerm_network_interface" "nic_win_01" {
  name                = "nic_win-01"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "nic_win-01-configuration"
    subnet_id                     = azurerm_subnet.vm_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

# Virtual machine attach NIC
resource "azurerm_windows_virtual_machine" "vm-win-01" {
  name                = "vm-win-01"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = "Standard_DS2_v2"
  admin_username      = "username"
  admin_password      = "password_1@aA"
  network_interface_ids = [
    azurerm_network_interface.nic_win_01.id
  ]

  os_disk {
    name                 = "disk-os-win-01"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-Datacenter"
    version   = "latest"
  }
}



# ---------------------------------------
# Bastion host

resource "azurerm_public_ip" "bastion_pip" {
  name                = "pip-bastion"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_bastion_host" "bastion_host" {
  name                = "bastion-host"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
  scale_units         = 2

  copy_paste_enabled     = true
  file_copy_enabled      = true
  shareable_link_enabled = true
  tunneling_enabled      = true

  ip_configuration {
    name                 = "config-01"
    subnet_id            = azurerm_subnet.bastion_subnet.id
    public_ip_address_id = azurerm_public_ip.bastion_pip.id
  }
}



# ---------------------------------------
# Azure Blob
resource "azurerm_storage_account" "sa" {
  name                     = "stracc"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "blob" {
  name                  = "blob"
  storage_account_name  = azurerm_storage_account.sa.name
  container_access_type = "private"
}
