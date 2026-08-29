import sys
import asyncio

filepath = "/opt/hermes/plugins/platforms/discord/adapter.py"
with open(filepath, "r") as f:
    code = f.read()

# Patch 1: Online status presence on_ready
target1 = """            @self._client.event
            async def on_ready():
                logger.info("[%s] Connected as %s", adapter_self.name, adapter_self._client.user)"""

replacement1 = """            @self._client.event
            async def on_ready():
                logger.info("[%s] Connected as %s", adapter_self.name, adapter_self._client.user)
                try:
                    import discord
                    await adapter_self._client.change_presence(status=discord.Status.online)
                    logger.info("[%s] Set Discord status to online", adapter_self.name)
                except Exception as pe:
                    logger.warning("[%s] Failed to set presence: %s", adapter_self.name, pe)"""

# Patch 2: typing loop and stop typing logic with generation guard
target2 = """    async def send_typing(self, chat_id: str, metadata=None) -> None:
        \"\"\"Start a persistent typing indicator for a channel.

        Discord's TYPING_START gateway event is unreliable in DMs for bots.
        Instead, start a background loop that hits the typing endpoint every
        12 seconds (typing indicator lasts ~10s).  The loop is cancelled when
        stop_typing() is called (after the response is sent).

        Rate-limit handling: if a 429 is encountered, the loop logs a
        warning, sleeps for the ``retry_after`` duration (or a sensible
        default), and continues — it does NOT die on a single rate-limit
        hit.  Only CancelledError (from stop_typing) stops the loop.
        \"\"\"
        if not self._client:
            return
        # Don't start a duplicate loop
        if chat_id in self._typing_tasks:
            return

        async def _typing_loop() -> None:
            try:
                while True:
                    try:
                        route = discord.http.Route(
                            "POST", "/channels/{channel_id}/typing",
                            channel_id=chat_id,
                        )
                        await self._client.http.request(route)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        # Don't die on 429 — backoff and continue
                        retry_after = self._extract_discord_retry_after(e)
                        if retry_after is not None:
                            logger.warning(
                                "Typing indicator rate-limited for %s; retrying in %.1fs",
                                chat_id, retry_after,
                            )
                        else:
                            logger.debug(
                                "Discord typing indicator failed for %s: %s",
                                chat_id, e,
                            )
                            return
                        await asyncio.sleep(retry_after)
                        continue
                    await asyncio.sleep(12)
            except asyncio.CancelledError:
                pass
            finally:
                self._typing_tasks.pop(chat_id, None)

        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())

    async def stop_typing(self, chat_id: str) -> None:
        \"\"\"Stop the persistent typing indicator for a channel.\"\"\"
        task = self._typing_tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass"""

replacement2 = """    async def send_typing(self, chat_id: str, metadata=None) -> None:
        \"\"\"Start a persistent typing indicator for a channel.

        Discord's TYPING_START gateway event is unreliable in DMs for bots.
        Instead, start a background loop that hits the typing endpoint every
        8 seconds (typing indicator lasts ~10s).  The loop is cancelled when
        stop_typing() is called (after the response is sent).
        \"\"\"
        if not self._client:
            return
        
        if not hasattr(self, "_typing_tasks"):
            self._typing_tasks = {}
        if not hasattr(self, "_typing_generations"):
            self._typing_generations = {}

        # Don't start a duplicate loop
        if chat_id in self._typing_tasks:
            return

        # Increment generation to mark a new active typing session
        gen = self._typing_generations.get(chat_id, 0) + 1
        self._typing_generations[chat_id] = gen

        async def _typing_loop(current_gen: int) -> None:
            try:
                while True:
                    if self._typing_generations.get(chat_id) != current_gen:
                        return
                    try:
                        route = discord.http.Route(
                            "POST", "/channels/{channel_id}/typing",
                            channel_id=chat_id,
                        )
                        await self._client.http.request(route)
                    except asyncio.CancelledError:
                        return
                    except Exception as e:
                        # Don't die on 429 — backoff and continue
                        retry_after = self._extract_discord_retry_after(e)
                        if retry_after is not None:
                            logger.warning(
                                "Typing indicator rate-limited for %s; retrying in %.1fs",
                                chat_id, retry_after,
                            )
                        else:
                            logger.debug(
                                "Discord typing indicator failed for %s: %s",
                                chat_id, e,
                            )
                            return
                        await asyncio.sleep(retry_after)
                        continue
                    
                    # Sleep in increments of 1 second up to 8 seconds total
                    for _ in range(8):
                        await asyncio.sleep(1)
                        if self._typing_generations.get(chat_id) != current_gen:
                            return
            except asyncio.CancelledError:
                pass
            finally:
                # Only pop if we are still the current generation
                if self._typing_generations.get(chat_id) == current_gen:
                    self._typing_tasks.pop(chat_id, None)

        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop(gen))

    async def stop_typing(self, chat_id: str) -> None:
        \"\"\"Stop the persistent typing indicator for a channel.\"\"\"
        if not hasattr(self, "_typing_generations"):
            self._typing_generations = {}
        # Invalidate any currently running loop
        self._typing_generations[chat_id] = self._typing_generations.get(chat_id, 0) + 1

        task = self._typing_tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass"""

if target1 in code:
    code = code.replace(target1, replacement1)
else:
    print("Target1 not found!")
    sys.exit(1)

if target2 in code:
    code = code.replace(target2, replacement2)
else:
    print("Target2 not found!")
    sys.exit(1)

with open(filepath, "w") as f:
    f.write(code)

print("Patched discord status successfully!")
