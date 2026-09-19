# Hex fixture review checklist

For the owner reviewing fixtures in `src/wjh/md/tests/fixtures/`. Fixtures are
the **only** check against the spec that doesn't depend on our code, so this review is on the critical path.

## For each fixture

- [ ] The header comment names the **spec document, version, section, and table**, and they
      match [spec tracking](../spec/README.md).
- [ ] The `MsgType` bytes match the spec's type code.
- [ ] The `MsgSize` bytes equal the spec's documented message length, and the fixture's
      total byte count equals `MsgSize`.
- [ ] Every field is present, **in order**, with the documented width.
- [ ] Multi-byte fields are **little-endian** (least significant byte first).
- [ ] Field values are distinctive (e.g. `OrderID = 0x0102030405060708`, not `1`),
      so an offset error of one byte or one field would be caught.
- [ ] Enum and character fields (side, status, …) use values the spec actually defines.
- [ ] Reserved or filler bytes are present and set to what the spec says.
- [ ] The expected decoded values listed in the test agree with the bytes.

## For the packet-header fixture

- [ ] `PktSize` covers the header plus all messages.
- [ ] `NumberMsgs` matches the number of messages that follow.
- [ ] `DeliveryFlag` value is taken from the spec's table.
- [ ] The send time layout (seconds + nanoseconds) matches the spec.

## Sign-off

Record the reviewer and date in the fixture file's header comment, then update the
status to ✅ in the [message catalog](../spec/message-catalog.md).
