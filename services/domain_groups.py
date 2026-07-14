"""Windows domain group lookups (NetAPI / LDAP)."""
from __future__ import annotations

from flask import current_app

def get_user_domain_groups_via_netapi(username, domain=None):
    """
    Get domain groups for a specific user using NetUserGetGroups
    This queries the domain controller directly for the user's groups
    """
    groups = []
    try:
        import win32net
        import win32netcon
        
        if not domain:
            import config
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else None
        
        # Get domain controller name
        try:
            dc_name = win32net.NetGetAnyDCName(None, domain)
        except:
            dc_name = None
        
        # Query user's groups from domain
        try:
            # NetUserGetGroups gets groups the user is a direct member of
            user_groups = win32net.NetUserGetGroups(dc_name, username)
            
            for group_info in user_groups:
                group_name = group_info.get('name', '')
                if group_name:
                    # Format: DOMAIN\\GroupName
                    if domain:
                        groups.append(f"{domain}\\{group_name}")
                    else:
                        groups.append(group_name)
        except Exception as e:
            print(f"Error getting user groups via NetUserGetGroups: {str(e)}")
            
            # Fallback: try NetUserGetLocalGroups on domain controller
            try:
                local_groups = win32net.NetUserGetLocalGroups(dc_name, username, 0)
                for group_name in local_groups:
                    if domain:
                        groups.append(f"{domain}\\{group_name}")
                    else:
                        groups.append(group_name)
            except:
                pass
        
    except Exception as e:
        print(f"Error in get_user_domain_groups_via_netapi: {str(e)}")
        return []
    
    return groups



def get_user_domain_groups(username, domain=None):
    """
    Get domain groups for a user using Windows API methods
    Primary method: get_token_groups() - reads from security token (includes nested groups)
    Secondary: get_local_groups() - gets local machine groups
    Returns a list of group names with domain prefix (e.g., ZIEBART\\GroupName)
    """
    user_groups = set()
    
    try:
        if not domain:
            import config
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else None
        
        # Method 1: Get token groups (PRIMARY METHOD - includes nested groups)
        # Returns: ['ZIEBART\\IT_Staff', 'ZIEBART\\Developers', 'BUILTIN\\Administrators', ...]
        token_groups = get_token_groups() or []
        if domain:
            domain_upper = domain.upper()
            for group in token_groups:
                # Only include groups from the user's domain (e.g., ZIEBART\...)
                if group.startswith(f"{domain_upper}\\"):
                    user_groups.add(group)
        else:
            # If no domain, include all token groups
            for group in token_groups:
                user_groups.add(group)
        
        # Method 2: Get local machine groups (these won't have domain prefix)
        local_groups = get_local_groups(username) or []
        for group in local_groups:
            # Only add if it's not already in domain groups
            if group not in [g.split('\\')[-1] for g in user_groups]:
                user_groups.add(group)
        
    except Exception as e:
        print(f"Error getting Windows groups: {str(e)}")
        return []
    
    # Return sorted list of unique group names
    # Domain groups will have format: ZIEBART\\GroupName
    # Local groups will just be: GroupName
    return sorted(list(user_groups))

def get_user_domain_groups_via_ldap(username, domain=None):
    """
    Get all domain groups for a user via LDAP (includes nested groups)
    This queries Active Directory for the user's memberOf attribute
    """
    groups = []
    try:
        from ldap3 import Server, Connection, ALL, SIMPLE
        import config
        
        if not domain:
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else 'YOURDOMAIN'
        
        # Get domain controller
        dc = config.DOMAIN_CONTROLLER if hasattr(config, 'DOMAIN_CONTROLLER') and config.DOMAIN_CONTROLLER else None
        if not dc:
            try:
                import win32net
                dc = win32net.NetGetAnyDCName(None, domain)
                if dc:
                    dc = dc.replace('\\\\', '')  # Remove leading backslashes
            except:
                try:
                    import socket
                    fqdn = socket.getfqdn()
                    dc = fqdn.split('.', 1)[1] if '.' in fqdn else domain.lower()
                except:
                    dc = domain.lower()
        
        # Build base DN
        base_dn = config.LDAP_BASE_DN if hasattr(config, 'LDAP_BASE_DN') and config.LDAP_BASE_DN else None
        if not base_dn:
            # Construct base DN from domain name
            base_dn = ','.join([f'DC={part}' for part in domain.lower().split('.')])
        
        # Connect to LDAP server
        server = Server(dc, get_info=ALL)
        
        # Use SIMPLE authentication (Windows integrated auth)
        try:
            conn = Connection(server, user='', password='', authentication=SIMPLE, auto_bind=True)
        except:
            # If that fails, try with domain\username
            try:
                conn = Connection(server, user=f'{domain}\\{username}', password='', authentication=SIMPLE, auto_bind=True)
            except:
                return []
        
        # Search for user's groups via memberOf attribute
        search_filter = f'(&(objectClass=user)(sAMAccountName={username}))'
        conn.search(base_dn, search_filter, attributes=['memberOf'])
        
        if conn.entries:
            entry = conn.entries[0]
            if hasattr(entry, 'memberOf') and entry.memberOf:
                for group_dn in entry.memberOf.values:
                    if group_dn:
                        # Extract group name from DN (CN=GroupName,OU=...,DC=...)
                        # Format: CN=GroupName,OU=Groups,DC=domain,DC=com
                        parts = group_dn.split(',')
                        for part in parts:
                            if part.startswith('CN='):
                                group_name = part.replace('CN=', '')
                                if domain:
                                    groups.append(f"{domain}\\{group_name}")
                                else:
                                    groups.append(group_name)
                                break
        
        conn.unbind()
        
    except Exception as e:
        print(f"Error getting user groups via LDAP: {str(e)}")
        return []
    
    return groups

