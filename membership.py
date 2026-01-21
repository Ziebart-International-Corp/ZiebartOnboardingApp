"""
Windows Domain Group Membership Module
Handles retrieval of user groups from Windows domain/Active Directory
"""
import win32security
import win32api
import win32net
import win32netcon


def get_local_groups(username):
    """
    Get local machine groups for a user
    Uses: win32net.NetUserGetLocalGroups()
    Returns: Local machine groups the user belongs to
    Example: Groups like "Administrators", "Users" on the local computer
    """
    groups = []
    try:
        # Get local groups for the user
        local_groups = win32net.NetUserGetLocalGroups(
            None,  # Server name (None = local machine)
            username,
            0  # Flags: 0 = return group names
        )
        
        if local_groups:
            groups.extend(local_groups)
    except Exception as e:
        # If it fails, return empty list (user might not have local groups)
        pass
    
    return groups


def get_token_groups():
    """
    Get domain groups from Windows Security Token
    Uses: Windows Security Token API
    Process:
    - Opens the current process token
    - Gets all security groups (SIDs) from the token
    - Converts each SID to a readable name using LookupAccountSid()
    Returns format: DOMAIN\\GroupName (e.g., ZIEBART\\IT_Staff)
    Returns: Domain groups and local groups from the user's security token
    Most important for domain groups - includes nested groups
    """
    groups = []
    try:
        # Open the current process token
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32security.TOKEN_QUERY | win32security.TOKEN_QUERY_SOURCE
        )
        
        # Get all security groups from the token
        groups_info = win32security.GetTokenInformation(token, win32security.TokenGroups)
        
        # Convert each SID to a readable group name
        for group_sid, attributes in groups_info:
            try:
                account_name, domain_name, account_type = win32security.LookupAccountSid(None, group_sid)
                
                # Filter for group types (exclude user accounts)
                if account_type in [
                    win32security.SidTypeGroup,
                    win32security.SidTypeWellKnownGroup,
                    win32security.SidTypeAlias,
                    win32security.SidTypeDomain
                ]:
                    # Format: DOMAIN\\GroupName
                    if domain_name and account_name:
                        groups.append(f"{domain_name}\\{account_name}")
                    elif account_name:
                        groups.append(account_name)
            except Exception:
                # Skip SIDs that can't be resolved
                pass
        
        # Close the token handle
        win32api.CloseHandle(token)
        
    except Exception as e:
        # If token method fails, return empty list
        print(f"Error getting token groups: {str(e)}")
        return []
    
    return groups


def get_all_domain_groups(domain=None):
    """
    Get all domain groups from the domain controller
    Uses: win32net.NetGroupEnum() on the domain controller
    Process:
    - Gets the domain controller name via NetGetAnyDCName()
    - Enumerates all groups from the domain controller
    Returns: All groups available in the domain (not specific to a user)
    """
    groups = []
    try:
        if not domain:
            import config
            domain = config.DOMAIN_NAME if hasattr(config, 'DOMAIN_NAME') else None
        
        # Get domain controller name
        dc_name = win32net.NetGetAnyDCName(None, domain)
        
        # Enumerate all groups from domain controller
        resume_handle = 0
        while True:
            result, data, total, resume_handle = win32net.NetGroupEnum(
                dc_name,
                0,  # Level 0 = basic group info
                resume_handle
            )
            
            for group_info in data:
                group_name = group_info.get('name', '')
                if group_name:
                    if domain:
                        groups.append(f"{domain}\\{group_name}")
                    else:
                        groups.append(group_name)
            
            if resume_handle == 0:
                break
                
    except Exception as e:
        print(f"Error getting all domain groups: {str(e)}")
        return []
    
    return groups
