// import blocks
import Header from "./header";
import Paragraph from "./paragraph";
import Card from "./card";
import Chart from "./chart";
import Shortcut from "./shortcut";
import Spacer from "./spacer";
import Onboarding from "./onboarding";

// import tunes
import HeaderSize from "./header_size";

vmraid.provide("vmraid.workspace_block");

vmraid.workspace_block.blocks = {
	header: Header,
	paragraph: Paragraph,
	card: Card,
	chart: Chart,
	shortcut: Shortcut,
	spacer: Spacer,
	onboarding: Onboarding,
};

vmraid.workspace_block.tunes = {
	header_size: HeaderSize,
};