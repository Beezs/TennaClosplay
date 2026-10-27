"""Show raw button, axis, and hat values from connected game controllers."""

try:
    import pygame
except ImportError as error:
    raise SystemExit(
        "Pygame is required. Install it with: py -3 -m pip install pygame"
    ) from error


WINDOW_SIZE = (900, 520)
BACKGROUND = (24, 27, 34)
FOREGROUND = (235, 239, 245)
MUTED = (160, 172, 188)
ACCENT = (117, 219, 181)


def add_controller(controllers, device_index):
    controller = pygame.joystick.Joystick(device_index)
    controller.init()
    controllers[controller.get_instance_id()] = controller


def controller_lines(controller):
    buttons = [
        str(index)
        for index in range(controller.get_numbuttons())
        if controller.get_button(index)
    ]
    button_text = ", ".join(buttons) if buttons else "none"
    lines = [
        (f"{controller.get_name()}  (buttons pressed: {button_text})", ACCENT)
    ]

    axes = [
        f"{index}={controller.get_axis(index):+.2f}"
        for index in range(controller.get_numaxes())
    ]
    if axes:
        lines.append(("  Axes: " + "  ".join(axes), FOREGROUND))

    hats = [
        f"{index}={controller.get_hat(index)}"
        for index in range(controller.get_numhats())
    ]
    if hats:
        lines.append(("  Hats/D-pad: " + "  ".join(hats), FOREGROUND))

    return lines


def main():
    pygame.display.init()
    pygame.font.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Controller Input Viewer")
    font = pygame.font.Font(None, 26)
    small_font = pygame.font.Font(None, 21)
    clock = pygame.time.Clock()

    controllers = {}
    for device_index in range(pygame.joystick.get_count()):
        add_controller(controllers, device_index)

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.JOYDEVICEADDED:
                    add_controller(controllers, event.device_index)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    controllers.pop(event.instance_id, None)

            screen.fill(BACKGROUND)
            y = 18
            title = font.render("Controller Input Viewer", True, FOREGROUND)
            screen.blit(title, (20, y))
            y += 34
            hint = small_font.render(
                "Press buttons to see their raw numbers. Esc closes this window.",
                True,
                MUTED,
            )
            screen.blit(hint, (20, y))
            y += 36

            if not controllers:
                message = font.render(
                    "No controller detected. Connect one to see its inputs.",
                    True,
                    FOREGROUND,
                )
                screen.blit(message, (20, y))
            else:
                for controller in controllers.values():
                    for text, color in controller_lines(controller):
                        if y + 28 > WINDOW_SIZE[1]:
                            break
                        rendered = small_font.render(text, True, color)
                        screen.blit(rendered, (20, y))
                        y += 26
                    y += 12

            pygame.display.flip()
            clock.tick(30)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
