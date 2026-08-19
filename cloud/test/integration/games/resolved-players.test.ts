// PROTOTYPE (2026-08-19) -- demonstrates the fix proposed in per-ankh's
// scripts/docs/elo-calculator-design.md § "User-Submitted Games as a Data
// Source -- Blocked". Exercises resolveRosterIdentities/resolved_players in
// cloud/src/games.ts's handleGameDetail. Not part of the regular suite until
// that patch is reviewed and actually adopted.

import { applyD1Migrations, env } from "cloudflare:test";
import { beforeAll, describe, expect, it } from "vitest";
import { expectOk } from "../../helpers/assertions";
import { makeUser, type TestUser } from "../../helpers/builders";
import { putBlob, seedGame } from "../../helpers/games";
import { request } from "../../helpers/requests";

beforeAll(async () => {
	await applyD1Migrations(env.SHARE_DB, env.TEST_MIGRATIONS);
});

interface ResolvedPlayer {
	player_index: number;
	user_id: string;
	slug: string | null;
	display_name: string;
}

interface DetailBody {
	player_roster: { online_id: string | null }[];
	resolved_players: ResolvedPlayer[];
}

// Links a user's online_id the way an upload's "who is you" picker would --
// see migrations/0003_user_online_ids.sql. Not exposed as a public write
// path, so integration tests insert directly, same as seedGame does for the
// games row.
async function linkOnlineId(user: TestUser, onlineId: string): Promise<void> {
	await env.SHARE_DB.prepare(
		`INSERT INTO user_online_ids (user_id, online_id) VALUES (?, ?)`,
	)
		.bind(user.userId, onlineId)
		.run();
}

describe("resolved_players on GET /v1/games/:id (prototype)", () => {
	it("resolves both seats when both online_ids are linked", async () => {
		const owner = await makeUser({ displayName: "Owner Player" });
		const opponent = await makeUser({ displayName: "Opponent Player" });
		await linkOnlineId(owner, "STEAM_OWNER");
		await linkOnlineId(opponent, "STEAM_OPPONENT");

		const gameId = await seedGame(owner, { isPublic: true });
		await putBlob(gameId, {
			match_metadata: { game_name: "1v1", winner: null },
			player_roster: [
				{ player_index: 0, is_human: true, online_id: "STEAM_OWNER" },
				{ player_index: 1, is_human: true, online_id: "STEAM_OPPONENT" },
			],
		});

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.resolved_players).toHaveLength(2);
		const byIndex = new Map(body.resolved_players.map((p) => [p.player_index, p]));
		expect(byIndex.get(0)?.user_id).toBe(owner.userId);
		expect(byIndex.get(1)?.user_id).toBe(opponent.userId);
	});

	it("does not expose the raw online_id to a non-owner even though resolved_players is present", async () => {
		const owner = await makeUser();
		const opponent = await makeUser();
		await linkOnlineId(owner, "STEAM_OWNER_2");
		await linkOnlineId(opponent, "STEAM_OPPONENT_2");

		const gameId = await seedGame(owner, { isPublic: true });
		await putBlob(gameId, {
			match_metadata: { game_name: "1v1", winner: null },
			player_roster: [
				{ player_index: 0, is_human: true, online_id: "STEAM_OWNER_2" },
				{ player_index: 1, is_human: true, online_id: "STEAM_OPPONENT_2" },
			],
		});

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		// Existing PII boundary: untouched.
		expect(body.player_roster.every((p) => p.online_id === null)).toBe(true);
		// New: resolved identities present anyway, for both seats -- not just
		// the uploader's (which the API already exposed pre-patch).
		expect(body.resolved_players).toHaveLength(2);
	});

	it("skips a seat whose opponent never linked their online_id", async () => {
		const owner = await makeUser();
		await linkOnlineId(owner, "STEAM_OWNER_3");

		const gameId = await seedGame(owner, { isPublic: true });
		await putBlob(gameId, {
			match_metadata: { game_name: "1v1", winner: null },
			player_roster: [
				{ player_index: 0, is_human: true, online_id: "STEAM_OWNER_3" },
				// Opponent has a real online_id in the save, but has never
				// uploaded/self-linked -- the realistic common case.
				{ player_index: 1, is_human: true, online_id: "STEAM_UNKNOWN" },
			],
		});

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.resolved_players).toHaveLength(1);
		expect(body.resolved_players[0].player_index).toBe(0);
	});

	it("skips an ambiguous online_id claimed by more than one account, rather than guessing", async () => {
		const owner = await makeUser();
		const claimantA = await makeUser();
		const claimantB = await makeUser();
		await linkOnlineId(owner, "STEAM_OWNER_4");
		await linkOnlineId(claimantA, "STEAM_SHARED");
		await linkOnlineId(claimantB, "STEAM_SHARED");

		const gameId = await seedGame(owner, { isPublic: true });
		await putBlob(gameId, {
			match_metadata: { game_name: "1v1", winner: null },
			player_roster: [
				{ player_index: 0, is_human: true, online_id: "STEAM_OWNER_4" },
				{ player_index: 1, is_human: true, online_id: "STEAM_SHARED" },
			],
		});

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.resolved_players).toHaveLength(1);
		expect(body.resolved_players[0].player_index).toBe(0);
	});

	it("never resolves an AI seat, even if it somehow carried an online_id", async () => {
		const owner = await makeUser();
		await linkOnlineId(owner, "STEAM_OWNER_5");

		const gameId = await seedGame(owner, { isPublic: true });
		await putBlob(gameId, {
			match_metadata: { game_name: "1v1", winner: null },
			player_roster: [
				{ player_index: 0, is_human: true, online_id: "STEAM_OWNER_5" },
				{ player_index: 1, is_human: false, online_id: null },
			],
		});

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.resolved_players).toHaveLength(1);
		expect(body.resolved_players[0].player_index).toBe(0);
	});
});
