def complete_stages(ticket_page) -> None:
    buttons = [
        "Mark Stage 1 as Complete",
        "Mark Stage 2 as Complete",
        "Mark Stage 3 as Complete",
        "Mark Stage 4 as Complete",
    ]
    
    for button_name in buttons:
        try:
            button = ticket_page.get_by_role("button", name=button_name)
            button.click(timeout=3000)
            print(f"Clicked: {button_name}")
        except Exception as e:
            print(f"Button '{button_name}' not available or already completed: {e}")